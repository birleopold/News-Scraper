import pytest
from datetime import datetime,timedelta
from ugwatch.db import connect,upsert_notice,EAT
from ugwatch.collectors import extract_deadline,canonical,category,public_url,collect_feed,collect_egp
from ugwatch import service
from helpers import insert,JsonClient,start_fake_run,insert_job,MONITOR_PAGE


def test_fetch_failure_preserves_records_and_logs(app,monkeypatch):
    insert(app)
    with connect(app.config['DATABASE']) as db: db.execute('UPDATE sources SET enabled=0 WHERE id!=1')
    def broken(source):raise ValueError('Blocked source')
    monkeypatch.setattr(service,'collect',broken)
    service.start_run(app.config['DATABASE'],background=False)
    with connect(app.config['DATABASE']) as db:
        assert db.execute('SELECT count(*) FROM notices').fetchone()[0]==1
        assert db.execute('SELECT state FROM runs').fetchone()[0]=='partial'
        assert db.execute('SELECT status FROM sources WHERE id=1').fetchone()[0]=='Needs attention'


def test_overlapping_fetch_is_not_started(app):
    from ugwatch.db import now
    with connect(app.config['DATABASE']) as db:db.execute("INSERT INTO runs(started_at,state) VALUES (?,'running')",(now(),))
    _,started=service.start_run(app.config['DATABASE'])
    assert not started


def test_source_health_flags_silent_breakage():
    from ugwatch.service import health
    assert health(5,0,None,'ok')==('OK','ok')
    assert health(0,0,None,'none')==('Empty','none')                         # never had results: just empty
    status,message=health(0,40,'2026-11-20T10:00:00+03:00','0 links.')
    assert status=='Needs attention' and 'found 40 records before (last good result 2026-11-20)' in message
    assert health(3,50,None,'x')[0]=='Needs attention'                       # sharp drop
    assert health(8,9,None,'x')[0]=='OK'                                      # small sources may vary


def test_quiet_source_counts_as_needing_attention(app,monkeypatch):
    path=app.config['DATABASE']
    with connect(path) as db:
        db.execute('UPDATE sources SET enabled=0 WHERE id!=1')
        db.execute('UPDATE sources SET last_good_count=12 WHERE id=1')
    monkeypatch.setattr(service,'collect',lambda s:([],'0 links found.'))
    service.start_run(path,background=False)
    with connect(path) as db:
        src=db.execute('SELECT status,message,last_good_count FROM sources WHERE id=1').fetchone()
        assert src['status']=='Needs attention' and src['last_good_count']==12
        assert db.execute('SELECT failed,state FROM runs').fetchone()[:]==(1,'partial')
    monkeypatch.setattr(service,'collect',lambda s:([dict(url=f'https://example.com/back{i}',title='Tender for road works',category='Tender') for i in range(3)],'ok'))
    service.start_run(path,background=False)
    with connect(path) as db:
        assert db.execute('SELECT status,last_good_count FROM sources WHERE id=1').fetchone()[:]==('OK',3)


def test_temporary_outage_is_flagged_only_when_it_persists():
    from ugwatch.service import failure
    from ugwatch.collectors import TemporaryError
    worked=dict(last_good_count=186,last_good_at='2026-11-22T20:16:00+03:00',fail_streak=0)
    status,message,streak=failure(TemporaryError("Couldn't look up the site's address."),worked)
    assert status=='Temporarily unavailable' and streak==1 and 'last good result 2026-11-22' in message
    assert failure(TemporaryError('x'),dict(worked,fail_streak=1))[0]=='Temporarily unavailable'
    status,message,streak=failure(TemporaryError('x'),dict(worked,fail_streak=2))
    assert status=='Needs attention' and streak==3 and 'Failed 3 fetches in a row' in message
    assert failure(TemporaryError('x'),dict(last_good_count=0,fail_streak=0))[0]=='Needs attention'   # never worked (e.g. URA)
    assert failure(ValueError('No readable notice links found.'),worked)[0]=='Needs attention'        # changed page


def test_fetch_run_reports_temporary_outages_separately(app,monkeypatch):
    from ugwatch.collectors import TemporaryError
    path=app.config['DATABASE']
    with connect(path) as db:
        db.execute('UPDATE sources SET enabled=0 WHERE id!=1')
        db.execute('UPDATE sources SET last_good_count=50 WHERE id=1')
    def offline(source): raise TemporaryError('The site did not respond in time.')
    monkeypatch.setattr(service,'collect',offline)
    service.start_run(path,background=False)
    with connect(path) as db:
        src=db.execute('SELECT status,fail_streak FROM sources WHERE id=1').fetchone()
        run=db.execute('SELECT failed,message FROM runs').fetchone()
    assert (src['status'],src['fail_streak'])==('Temporarily unavailable',1)
    assert run['failed']==0 and '1 temporarily unavailable' in run['message']


def test_automatic_backups_are_daily_and_pruned(tmp_path):
    import os,time
    from ugwatch.backup import maybe_auto_backup,auto_backups,make_backup
    from ugwatch.db import init_db
    path=tmp_path/'watch.sqlite3'; init_db(path)
    manual=make_backup(path)
    first=maybe_auto_backup(path)
    assert first and maybe_auto_backup(path) is None                           # not again within the day
    with connect(first) as db: assert db.execute('SELECT count(*) FROM settings').fetchone()[0]>=2
    for i,old in enumerate(auto_backups(path)):
        os.utime(old,(time.time()-90000,time.time()-90000))
    for _ in range(3):
        for b in auto_backups(path): os.utime(b,(time.time()-90000,)*2)
        time.sleep(0.01); maybe_auto_backup(path,keep=2)
    assert len(auto_backups(path))==2 and manual.exists()                      # pruned autos, kept manual
