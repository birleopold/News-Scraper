import pytest
from datetime import datetime,timedelta
from ugwatch.db import connect,upsert_notice,EAT
from ugwatch.collectors import extract_deadline,canonical,category,public_url,collect_feed,collect_egp
from ugwatch import service
from helpers import insert,JsonClient,start_fake_run,insert_job,MONITOR_PAGE


def test_seed_migrates_bundled_sources_but_not_custom(tmp_path):
    from ugwatch.db import init_db
    from ugwatch.sources import seed
    path=tmp_path/'old.sqlite3'; init_db(path)
    with connect(path) as db:
        db.execute("INSERT INTO sources(name,url,kind,group_name,enabled,status) VALUES ('PPDA • bid invitations','https://gpp.ppda.go.ug/public/bid-invitations','html','Official',0,'Needs attention')")
        db.execute("INSERT INTO sources(name,url,kind,group_name) VALUES ('Bank of Uganda • procurement','https://example.com/mine','rss','Custom')")
        seed(db)
        ppda=db.execute("SELECT kind,enabled,status FROM sources WHERE name='PPDA • bid invitations'").fetchone()
        assert (ppda['kind'],ppda['enabled'],ppda['status'])==('ppda',0,'Not checked')
        assert db.execute("SELECT kind FROM sources WHERE url='https://example.com/mine'").fetchone()[0]=='rss'
        assert db.execute("SELECT count(*) FROM sources WHERE name='New Vision • notices'").fetchone()[0]==1


def test_saved_monitor_page_parsing():
    from ugwatch.collectors import parse_listing
    items=parse_listing(MONITOR_PAGE,'https://www.monitor.co.ug/uganda/jobs/tenders',{'name':'Daily Monitor • tenders','kind':'import_tenders'})
    titles=[i['title'] for i in items]
    assert len(items)==2 and titles[0].startswith('UGANDA CHRISTIAN UNIVERSITY')
    assert items[0]['category']=='Tender' and 'Finance, Build, Operate' in items[0]['excerpt']
    assert items[1]['category']=='Tender'                                         # no keyword, but on the tenders page
    assert not any('Subscribe' in t or 'ANNIVERSARY' in t for t in titles)


def test_import_saved_page_endpoint(app,client):
    h={'X-CSRF-Token':client.csrf}
    with connect(app.config['DATABASE']) as db:
        src=db.execute("SELECT id,status,kind FROM sources WHERE name='Daily Monitor • tenders'").fetchone()
    assert (src['status'],src['kind'])==('Import only','import_tenders')
    import io as _io
    send=lambda body,headers=h:client.post(f'/api/sources/{src["id"]}/import',data={'page':(_io.BytesIO(body),'tenders.html')},headers=headers,content_type='multipart/form-data')
    assert send(MONITOR_PAGE,{}).status_code==403
    assert client.post(f'/api/sources/{src["id"]}/import',headers=h).status_code==400
    wrong=MONITOR_PAGE.replace(b'www.monitor.co.ug/uganda/jobs/tenders',b'www.newvision.co.ug/opportunities')
    r=send(wrong); assert r.status_code==400 and 'newvision' in r.json['error']
    r=send(MONITOR_PAGE); assert r.status_code==200 and (r.json['found'],r.json['added'])==(2,2)
    assert send(MONITOR_PAGE).json['added']==0                                   # re-import adds nothing twice
    with connect(app.config['DATABASE']) as db:
        assert db.execute("SELECT status FROM sources WHERE id=?",(src['id'],)).fetchone()[0]=='Imported'
    cur=client.get('/api/notices?status=current').json
    assert cur['total']==2                                                        # imported adverts are current, not backlog


def test_first_fetch_backlog_is_not_current_but_later_additions_are(app,client,monkeypatch):
    path=app.config['DATABASE']
    with connect(path) as db:
        sid=db.execute("SELECT id FROM sources WHERE name='UNOC • tenders'").fetchone()[0]
        db.execute('UPDATE sources SET enabled=0 WHERE id!=?',(sid,))
    page=[dict(url='https://unoc.example/old',title='Invitation to bid for consultancy services',category='Tender')]
    monkeypatch.setattr(service,'collect',lambda s:(list(page),'ok'))
    service.start_run(path,background=False)
    assert client.get('/api/notices?status=current').json['total']==0
    assert client.get('/api/notices').json['total']==1                          # kept and searchable
    page.append(dict(url='https://unoc.example/new',title='Invitation to bid for pipeline survey works',category='Tender'))
    service.start_run(path,background=False)
    cur=client.get('/api/notices?status=current').json
    assert [r['url'] for r in cur['items']]==['https://unoc.example/new']


def test_import_only_sources_are_never_fetched(app,monkeypatch):
    seen=[]
    monkeypatch.setattr(service,'collect',lambda s:(seen.append(s['kind']),([],'ok'))[1])
    service.start_run(app.config['DATABASE'],background=False)
    assert seen and not any(k.startswith('import_') for k in seen)
