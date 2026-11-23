import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from .alerts import notify_run, send_reminders
from .backup import maybe_auto_backup
from .enrich import enrich, reclassify
from .collectors import TemporaryError, collect
from .db import connect, now, EAT, upsert_notice

log=logging.getLogger(__name__)


QUICK_KINDS={'disposals':('egp_disposal',)}
QUICK_EVERY=timedelta(minutes=60)


def start_run(path, background=True, scope='full'):
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        cutoff=(datetime.now(EAT)-timedelta(hours=2)).isoformat()
        db.execute("UPDATE runs SET state='interrupted',finished_at=?,message='Previous fetch did not finish.' WHERE state='running' AND started_at<?",(now(),cutoff))
        active=db.execute("SELECT id FROM runs WHERE state='running'").fetchone()
        if active: return active['id'],False
        run_id=db.execute("INSERT INTO runs(started_at,state,scope) VALUES (?,'running',?)",(now(),scope)).lastrowid
    if background:
        threading.Thread(target=fetch_all,args=(path,run_id,scope),daemon=True,name='news-fetch').start()
    else: fetch_all(path,run_id,scope)
    return run_id,True


def health(count,last_good,last_good_at,message):
    """Status for a source that answered: flag silent breakage instead of reporting a normal 'Empty'."""
    since=f' (last good result {last_good_at[:10]})' if last_good_at else ''
    if count==0 and last_good:
        return 'Needs attention',f'Returned nothing, but found {last_good} records before{since}. The site may have changed its layout or feed; open it to check. '+message
    if last_good>=10 and count<last_good*0.2:
        return 'Needs attention',f'Found only {count}, down from {last_good}{since}. The site may have changed; open it to check. '+message
    return ('OK' if count else 'Empty'),message


FLAG_AFTER=3


def failure(exc,source):
    """Status for a source that failed. A network hiccup at a source that has worked
    before is 'Temporarily unavailable' until it fails FLAG_AFTER fetches in a row;
    blocks, changed pages and never-working sources need attention straight away."""
    streak=(source.get('fail_streak') or 0)+1
    last_good=source.get('last_good_at')
    if isinstance(exc,TemporaryError) and source.get('last_good_count') and streak<FLAG_AFTER:
        return ('Temporarily unavailable',
                f'{exc} It worked before{" (last good result "+last_good[:10]+")" if last_good else ""} and will be retried on the next fetch; '
                f'it is flagged if it fails {FLAG_AFTER} times in a row (now {streak}).',streak)
    note=f' Failed {streak} fetches in a row.' if streak>1 and isinstance(exc,TemporaryError) else ''
    return 'Needs attention',f'{exc}{note}',streak


def fetch_all(path,run_id,scope='full'):
    added=checked=failed=temporary=0
    try:
        with connect(path) as db:
            # Import-only sources block automated access; they are filled from saved pages.
            sources=[dict(r) for r in db.execute("SELECT * FROM sources WHERE enabled=1 AND kind NOT LIKE 'import_%'")]
        if scope in QUICK_KINDS: sources=[s for s in sources if s['kind'] in QUICK_KINDS[scope]]
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures={pool.submit(collect,s):s for s in sources}
            for future in as_completed(futures):
                source=futures[future]; checked+=1
                try:
                    items,message=future.result()
                    status,message=health(len(items),source.get('last_good_count') or 0,source.get('last_good_at'),message)
                    first_fetch=not source.get('last_good_count') and not source.get('last_good_at')
                    with connect(path) as db:
                        new=sum(upsert_notice(db,source['id'],dict(item,baseline=first_fetch)) for item in items)
                        db.execute("UPDATE sources SET last_checked=?,last_success=?,status=?,message=?,item_count=?,fail_streak=0 WHERE id=?",
                                   (now(),now(),status,message,len(items),source['id']))
                        if items:
                            db.execute('UPDATE sources SET last_good_count=?,last_good_at=? WHERE id=?',(len(items),now(),source['id']))
                    if status=='Needs attention': failed+=1
                    added+=new
                except Exception as exc:
                    status,message,streak=failure(exc,source)
                    if status=='Needs attention': failed+=1
                    else: temporary+=1
                    log.warning('%s: %s',source['name'],exc)
                    with connect(path) as db:
                        db.execute('UPDATE sources SET last_checked=?,status=?,message=?,fail_streak=? WHERE id=?',(now(),status,message[:600],streak,source['id']))
                with connect(path) as db:
                    db.execute('UPDATE runs SET added=?,checked=?,failed=? WHERE id=?',(added,checked,failed,run_id))
        summary=('Hourly disposal check: ' if scope!='full' else '')+f'{checked} sources checked; {failed} need attention'+(f'; {temporary} temporarily unavailable' if temporary else '')+'.'
        with connect(path) as db:
            db.execute('UPDATE runs SET state=?,finished_at=?,message=? WHERE id=?',('partial' if failed or temporary else 'complete',now(),summary,run_id))
        # Read new advert PDFs before alerting, so disposals hidden behind vague titles are found.
        enrich(path)
        with connect(path) as db: reclassify(db)
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
                last=db.execute("SELECT started_at FROM runs WHERE scope='full' ORDER BY id DESC LIMIT 1").fetchone()
                latest=db.execute('SELECT started_at FROM runs ORDER BY id DESC LIMIT 1').fetchone()
            send_reminders(path)
            if settings['auto_fetch']!='1': continue
            age=lambda row: datetime.now(EAT)-datetime.fromisoformat(row['started_at']) if row else timedelta.max
            if age(last)>=timedelta(minutes=int(settings['interval_minutes'])): start_run(path)
            # Between full fetches, check eGP's official disposal list every hour (disposals come first).
            elif age(latest)>=QUICK_EVERY: start_run(path,scope='disposals')
        except Exception: log.exception('Scheduler error')
