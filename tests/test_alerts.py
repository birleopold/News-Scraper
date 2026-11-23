import pytest
from datetime import datetime,timedelta
from ugwatch.db import connect,upsert_notice,EAT
from ugwatch.collectors import extract_deadline,canonical,category,public_url,collect_feed,collect_egp
from ugwatch import service
from helpers import insert,JsonClient,start_fake_run,insert_job,MONITOR_PAGE


def test_alerts_summarise_new_keyword_matches_only(app):
    from ugwatch.alerts import notify_run
    path=app.config['DATABASE']
    insert(app,url='https://example.com/old-match',title='Old computers tender')       # before the run: never re-alerted
    with connect(path) as db:
        db.execute("UPDATE notices SET first_seen='2000-01-01T00:00:00+03:00'")
        db.execute("INSERT INTO watchwords(term) VALUES ('computers')")
        db.execute("UPDATE settings SET value='matches' WHERE key='alert_mode'")
    run_id=start_fake_run(app)
    insert(app,url='https://example.com/new-match',title='Supply of <laptops> & computers')
    insert(app,url='https://example.com/new-other',title='Supply of furniture')
    insert(app,url='https://example.com/new-result',title='Best evaluated bidder: computers',deadline=None,deadline_origin='listing')
    sent=[]
    assert notify_run(path,run_id,sender=lambda *a:(sent.append(a),(True,'ok'))[1])==1
    title,body,url=sent[0]
    assert title=='1 new keyword match' and 'Supply of <laptops> & computers' in body and '(closes' in body
    assert url=='http://127.0.0.1:5050/?view=matches'
    with connect(path) as db:
        assert '1 new keyword match' in db.execute("SELECT value FROM settings WHERE key='last_alert'").fetchone()[0]


def test_alert_modes_open_and_off_and_empty_watchlist(app):
    from ugwatch.alerts import notify_run
    path=app.config['DATABASE']
    run_id=start_fake_run(app)
    for i in range(5): insert(app,url=f'https://example.com/open-{i}',title=f'Tender number {i}')
    insert(app,url='https://example.com/undated',deadline=None,deadline_origin='listing')
    sent=[]; sender=lambda *a:(sent.append(a),(True,'ok'))[1]
    assert notify_run(path,run_id,sender=sender)==0 and not sent          # default 'matches' with no keywords stays quiet
    with connect(path) as db: db.execute("UPDATE settings SET value='open' WHERE key='alert_mode'")
    assert notify_run(path,run_id,sender=sender)==5
    assert sent[0][0]=='5 new open opportunities' and '+ 2 more' in sent[0][1]
    with connect(path) as db: db.execute("UPDATE settings SET value='off' WHERE key='alert_mode'")
    assert notify_run(path,run_id,sender=sender)==0 and len(sent)==1


def test_alert_failure_is_recorded_not_raised(app):
    from ugwatch.alerts import notify_run
    path=app.config['DATABASE']
    with connect(path) as db: db.execute("UPDATE settings SET value='open' WHERE key='alert_mode'")
    run_id=start_fake_run(app); insert(app)
    assert notify_run(path,run_id,sender=lambda *a:(False,'Windows refused the notification: blocked'))==0
    def boom(*a): raise RuntimeError('unexpected')
    assert notify_run(path,run_id,sender=boom)==0
    with connect(path) as db:
        assert 'blocked' in db.execute("SELECT value FROM settings WHERE key='last_alert'").fetchone()[0]


def test_alert_settings_api(app,client,monkeypatch):
    from ugwatch import alerts
    h={'X-CSRF-Token':client.csrf}
    assert client.get('/api/overview').json['settings']['alert_mode']=='disposals'
    assert client.patch('/api/alerts',json={'mode':'loud'},headers=h).status_code==400
    assert client.patch('/api/alerts',json={'mode':'off'}).status_code==403
    assert client.patch('/api/alerts',json={'mode':'open'},headers=h).status_code==200
    assert client.get('/api/overview').json['settings']['alert_mode']=='open'
    monkeypatch.setattr(alerts,'send_toast',lambda *a:(True,'Notification shown.'))
    r=client.post('/api/alerts/test',json={},headers=h)
    assert r.status_code==200 and r.json['ok']


def test_fetch_run_triggers_alert(app,monkeypatch):
    from ugwatch import alerts
    path=app.config['DATABASE']
    with connect(path) as db:
        db.execute('UPDATE sources SET enabled=0 WHERE id!=1')
        db.execute("UPDATE settings SET value='open' WHERE key='alert_mode'")
    future=(datetime.now(EAT).date()+timedelta(days=4)).isoformat()
    monkeypatch.setattr(service,'collect',lambda s:([dict(url='https://example.com/fresh',title='Tender for road works',category='Tender',deadline=future,deadline_origin='official')],'ok'))
    sent=[]
    monkeypatch.setattr(alerts,'send_toast',lambda *a:(sent.append(a),(True,'ok'))[1])
    service.start_run(path,background=False)
    assert sent and sent[0][0]=='1 new open opportunity'


def test_old_default_alert_mode_moves_to_disposals_once(tmp_path):
    from ugwatch.db import init_db
    path=tmp_path/'old.sqlite3'; init_db(path)
    with connect(path) as db:
        db.execute("UPDATE settings SET value='matches' WHERE key='alert_mode'")
        db.execute("DELETE FROM settings WHERE key='alert_mode_v2'")
    init_db(path)
    with connect(path) as db: assert db.execute("SELECT value FROM settings WHERE key='alert_mode'").fetchone()[0]=='disposals'
    with connect(path) as db: db.execute("UPDATE settings SET value='matches' WHERE key='alert_mode'")   # user picks matches later
    init_db(path)
    with connect(path) as db: assert db.execute("SELECT value FROM settings WHERE key='alert_mode'").fetchone()[0]=='matches'
