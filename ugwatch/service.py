import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from .alerts import notify_run
from .backup import maybe_auto_backup
from .collectors import collect
from .db import connect, now, EAT, upsert_notice

log=logging.getLogger(__name__)


def start_run(path, background=True):
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        cutoff=(datetime.now(EAT)-timedelta(hours=2)).isoformat()
        db.execute("UPDATE runs SET state='interrupted',finished_at=?,message='Previous fetch did not finish.' WHERE state='running' AND started_at<?",(now(),cutoff))
        active=db.execute("SELECT id FROM runs WHERE state='running'").fetchone()
        if active: return active['id'],False
        run_id=db.execute("INSERT INTO runs(started_at,state) VALUES (?,'running')",(now(),)).lastrowid
    if background:
        threading.Thread(target=fetch_all,args=(path,run_id),daemon=True,name='news-fetch').start()
    else: fetch_all(path,run_id)
    return run_id,True


def health(count,last_good,last_good_at,message):
    """Status for a source that answered: flag silent breakage instead of reporting a normal 'Empty'."""
    since=f' (last good result {last_good_at[:10]})' if last_good_at else ''
    if count==0 and last_good:
        return 'Needs attention',f'Returned nothing, but found {last_good} records before{since}. The site may have changed its layout or feed; open it to check. '+message
    if last_good>=10 and count<last_good*0.2:
        return 'Needs attention',f'Found only {count}, down from {last_good}{since}. The site may have changed; open it to check. '+message
    return ('OK' if count else 'Empty'),message


def fetch_all(path,run_id):
    added=checked=failed=0
    try:
        with connect(path) as db:
            sources=[dict(r) for r in db.execute('SELECT * FROM sources WHERE enabled=1')]
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures={pool.submit(collect,s):s for s in sources}
            for future in as_completed(futures):
                source=futures[future]; checked+=1
                try:
                    items,message=future.result()
                    status,message=health(len(items),source.get('last_good_count') or 0,source.get('last_good_at'),message)
                    with connect(path) as db:
                        new=sum(upsert_notice(db,source['id'],item) for item in items)
                        db.execute("UPDATE sources SET last_checked=?,last_success=?,status=?,message=?,item_count=? WHERE id=?",
                                   (now(),now(),status,message,len(items),source['id']))
                        if items:
                            db.execute('UPDATE sources SET last_good_count=?,last_good_at=? WHERE id=?',(len(items),now(),source['id']))
                    if status=='Needs attention': failed+=1
                    added+=new
                except Exception as exc:
                    failed+=1
                    log.warning('%s: %s',source['name'],exc)
                    with connect(path) as db:
                        db.execute("UPDATE sources SET last_checked=?,status='Needs attention',message=? WHERE id=?",(now(),str(exc)[:450],source['id']))
                with connect(path) as db:
                    db.execute('UPDATE runs SET added=?,checked=?,failed=? WHERE id=?',(added,checked,failed,run_id))
        with connect(path) as db:
            db.execute('UPDATE runs SET state=?,finished_at=?,message=? WHERE id=?',('partial' if failed else 'complete',now(),f'{checked} sources checked; {failed} need attention.',run_id))
        if added: notify_run(path,run_id)
        maybe_auto_backup(path)
    except Exception:
        log.exception('Fetch failed')
        with connect(path) as db:
            db.execute("UPDATE runs SET state='failed',finished_at=?,message='Unexpected fetch error; see application log.' WHERE id=?",(now(),run_id))


def scheduler(path,stop):
    while not stop.wait(30):
        try:
            with connect(path) as db:
                settings=dict(db.execute('SELECT key,value FROM settings').fetchall())
                last=db.execute('SELECT started_at FROM runs ORDER BY id DESC LIMIT 1').fetchone()
            if settings['auto_fetch']!='1': continue
            due=not last or datetime.now(EAT)-datetime.fromisoformat(last['started_at'])>=timedelta(minutes=int(settings['interval_minutes']))
            if due: start_run(path)
        except Exception: log.exception('Scheduler error')
