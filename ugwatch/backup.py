"""Consistent online SQLite backups, manual or automatic (daily, pruned)."""
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)
AUTO_PREFIX = 'uganda_watch_auto_'
KEEP_AUTO = 14
AUTO_EVERY_HOURS = 20


def make_backup(database, auto=False):
    """Copy the live database with SQLite's backup API; safe while the app is running."""
    database = Path(database)
    folder = database.parent / 'backups'
    folder.mkdir(exist_ok=True)
    target = folder / f"{AUTO_PREFIX if auto else 'uganda_watch_'}{datetime.now():%Y%m%d_%H%M%S_%f}.sqlite3"
    # sqlite3's context manager only commits; close explicitly so Windows releases the files.
    src, dst = sqlite3.connect(database), sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    return target


def auto_backups(database):
    folder = Path(database).parent / 'backups'
    return sorted(folder.glob(AUTO_PREFIX + '*.sqlite3')) if folder.exists() else []


def maybe_auto_backup(database, keep=KEEP_AUTO, every_hours=AUTO_EVERY_HOURS):
    """Back up if the newest automatic backup is old enough, then prune old automatic ones.

    Manual backups (backup.py) are never pruned. Never raises: a failed backup must not
    break fetching. Returns the new backup path or None."""
    try:
        existing = auto_backups(database)
        if existing and time.time() - existing[-1].stat().st_mtime < every_hours * 3600:
            return None
        target = make_backup(database, auto=True)
        for old in auto_backups(database)[:-keep]:
            old.unlink()
        log.info('Automatic backup saved: %s', target)
        return target
    except Exception:
        log.exception('Automatic backup failed')
        return None
