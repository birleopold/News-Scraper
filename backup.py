"""Create a consistent online SQLite backup without stopping the app."""
import sqlite3
from datetime import datetime
from pathlib import Path


def main():
    root=Path(__file__).resolve().parent/'data'
    source=root/'uganda_watch.sqlite3'
    if not source.exists(): raise SystemExit('No database yet. Start the application first.')
    target=root/'backups'/f'uganda_watch_{datetime.now():%Y%m%d_%H%M%S_%f}.sqlite3'
    target.parent.mkdir(exist_ok=True)
    with sqlite3.connect(source) as src,sqlite3.connect(target) as dst: src.backup(dst)
    print(f'Backup saved: {target}')


if __name__=='__main__': main()
