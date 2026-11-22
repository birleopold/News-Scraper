import sqlite3
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

EAT = ZoneInfo('Africa/Kampala')


def now():
    return datetime.now(EAT).isoformat(timespec='seconds')


@contextmanager
def connect(path):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS sources (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
          kind TEXT NOT NULL, group_name TEXT NOT NULL DEFAULT 'Custom',
          enabled INTEGER NOT NULL DEFAULT 1, last_checked TEXT,
          last_success TEXT, status TEXT NOT NULL DEFAULT 'Not checked',
          message TEXT NOT NULL DEFAULT '', item_count INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS notices (
          id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id),
          url TEXT NOT NULL UNIQUE, title TEXT NOT NULL, excerpt TEXT NOT NULL DEFAULT '',
          category TEXT NOT NULL, publisher TEXT NOT NULL DEFAULT '',
          published_at TEXT, deadline TEXT, deadline_evidence TEXT NOT NULL DEFAULT '',
          deadline_origin TEXT NOT NULL DEFAULT '', reference TEXT NOT NULL DEFAULT '',
          organization TEXT NOT NULL DEFAULT '', first_seen TEXT NOT NULL,
          last_seen TEXT NOT NULL, saved INTEGER NOT NULL DEFAULT 0,
          read INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '',
          user_deadline TEXT, deadline_reviewed INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS idx_deadline ON notices(deadline);
        CREATE INDEX IF NOT EXISTS idx_seen ON notices(first_seen);
        CREATE TABLE IF NOT EXISTS notice_sources (
          notice_id INTEGER NOT NULL REFERENCES notices(id),
          source_id INTEGER NOT NULL REFERENCES sources(id),
          last_seen TEXT NOT NULL, PRIMARY KEY(notice_id,source_id));
        CREATE TABLE IF NOT EXISTS watchwords (id INTEGER PRIMARY KEY, term TEXT NOT NULL UNIQUE COLLATE NOCASE);
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
          state TEXT NOT NULL, added INTEGER NOT NULL DEFAULT 0,
          checked INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
          message TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        db.execute("INSERT OR IGNORE INTO settings VALUES ('interval_minutes','180')")
        db.execute("INSERT OR IGNORE INTO settings VALUES ('auto_fetch','1')")
        db.execute("INSERT OR IGNORE INTO settings VALUES ('alert_mode','matches')")
        # Remember each source's last non-empty result so a silent breakage can be flagged.
        columns={r['name'] for r in db.execute('PRAGMA table_info(sources)')}
        if 'last_good_count' not in columns:
            db.execute('ALTER TABLE sources ADD COLUMN last_good_count INTEGER NOT NULL DEFAULT 0')
            db.execute('ALTER TABLE sources ADD COLUMN last_good_at TEXT')
            db.execute('UPDATE sources SET last_good_count=item_count,last_good_at=last_success WHERE item_count>0')


def upsert_notice(db, source_id, item):
    fields = ['url','title','excerpt','category','publisher','published_at','deadline',
              'deadline_evidence','deadline_origin','reference','organization']
    data = {k: item.get(k, '' if k not in ('published_at','deadline') else None) for k in fields}
    existing = db.execute('SELECT id,deadline_origin FROM notices WHERE url=?', (data['url'],)).fetchone()
    stamp = now()
    if existing:
        # User annotations and reviewed deadlines survive refreshes.
        priority={'official':4,'extracted':3,'feed':2,'listing':1,'discovery':0}
        if priority.get(data['deadline_origin'],0)>=priority.get(existing['deadline_origin'],0):
            db.execute('UPDATE notices SET '+','.join(f'{k}=?' for k in fields if k != 'url')+
                       ',source_id=?,last_seen=? WHERE id=?', [data[k] for k in fields if k != 'url']+[source_id,stamp,existing['id']])
        else:
            db.execute('UPDATE notices SET last_seen=? WHERE id=?',(stamp,existing['id']))
        db.execute('INSERT OR REPLACE INTO notice_sources VALUES (?,?,?)',(existing['id'],source_id,stamp))
        return 0
    cur=db.execute('INSERT INTO notices (source_id,'+','.join(fields)+',first_seen,last_seen) VALUES ('+
                   ','.join('?' for _ in range(len(fields)+3))+')', [source_id]+list(data.values())+[stamp,stamp])
    db.execute('INSERT INTO notice_sources VALUES (?,?,?)',(cur.lastrowid,source_id,stamp))
    return 1
