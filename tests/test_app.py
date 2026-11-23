import pytest
from datetime import datetime,timedelta
from ugwatch.app import create_app
from ugwatch.db import connect,upsert_notice,EAT
from ugwatch.collectors import extract_deadline,canonical,category,public_url,collect_feed,collect_egp
from ugwatch import service


@pytest.fixture
def app(tmp_path):
    app=create_app(tmp_path/'test.sqlite3');app.config['TESTING']=True
    return app


@pytest.fixture
def client(app):
    c=app.test_client();c.get('/')
    with c.session_transaction() as s: c.csrf=s['csrf']
    return c


def insert(app,**overrides):
    item=dict(url='https://example.com/notice',title='Tender for office computers',category='Tender',deadline_origin='official',deadline=(datetime.now(EAT).date()+timedelta(days=3)).isoformat())
    item.update(overrides)
    with connect(app.config['DATABASE']) as db:
        upsert_notice(db,1,item)
        return db.execute('SELECT id FROM notices WHERE url=?',(item['url'],)).fetchone()['id']


def test_empty_workspace(client):
    assert client.get('/').status_code==200
    assert client.get('/api/notices').json['total']==0
    assert len(client.get('/api/overview').json['sources'])>=13


def test_dates_unknown_expired_and_due_today(app,client):
    insert(app)
    insert(app,url='https://example.com/unknown',deadline=None)
    insert(app,url='https://example.com/extracted',deadline_origin='extracted')
    insert(app,url='https://example.com/expired',deadline='2020-01-01')
    insert(app,url='https://example.com/today',deadline=datetime.now(EAT).date().isoformat())
    assert client.get('/api/notices?status=open').json['total']==2
    assert client.get('/api/notices?status=review').json['total']==2
    assert client.get('/api/notices?status=expired').json['total']==1


def test_dedup_preserves_user_data_and_authoritative_date(app,client):
    id=insert(app)
    client.patch(f'/api/notices/{id}',json={'saved':True,'notes':'Contact buyer','user_deadline':'2030-01-01'},headers={'X-CSRF-Token':client.csrf})
    with connect(app.config['DATABASE']) as db:
        assert upsert_notice(db,2,dict(url='https://example.com/notice',title='Search headline',category='Business',deadline_origin='discovery'))==0
    row=client.get('/api/notices').json['items'][0]
    assert row['saved']==1 and row['notes']=='Contact buyer'
    assert row['effective_deadline']=='2030-01-01' and row['deadline_origin']=='official'
    assert row['title']=='Tender for office computers'


def test_manual_review_and_reset(app,client):
    id=insert(app,deadline_origin='extracted')
    headers={'X-CSRF-Token':client.csrf}
    assert client.patch(f'/api/notices/{id}',json={'user_deadline':'2030-12-01'},headers=headers).status_code==200
    assert client.get('/api/notices?status=open').json['total']==1
    client.patch(f'/api/notices/{id}',json={'reset_deadline':True},headers=headers)
    assert client.get('/api/notices?status=review').json['total']==1


def test_csrf_and_bad_input(app,client):
    id=insert(app)
    assert client.patch(f'/api/notices/{id}',json={'saved':True}).status_code==403
    h={'X-CSRF-Token':client.csrf}
    assert client.patch(f'/api/notices/{id}',json={'user_deadline':'tomorrow'},headers=h).status_code==400
    assert client.patch('/api/settings',json={'auto_fetch':True,'interval_minutes':0},headers=h).status_code==400
    assert client.get('/api/notices?page=bad').status_code==400
    assert client.get('/api/notices?from=bad').status_code==400


def test_watchlist_and_search(app,client):
    insert(app)
    h={'X-CSRF-Token':client.csrf}
    client.post('/api/watchwords',json={'term':'COMPUTERS'},headers=h)
    assert client.get('/api/notices?view=matches').json['total']==1
    assert client.get('/api/notices?q=missing').json['total']==0


def test_export_formula_injection(app,client):
    insert(app,title='=HYPERLINK("evil")')
    r=client.get('/api/export')
    assert "'=HYPERLINK" in r.text and 'attachment' in r.headers['Content-Disposition']


def test_public_urls_reject_private():
    for url in ['http://127.0.0.1','http://[::1]','file:///tmp/a','http://user:password@example.com','http://192.168.1.2','http://localhost:5050']:
        with pytest.raises(ValueError): public_url(url)


def test_deadline_requires_explicit_label_and_year():
    assert extract_deadline('Published 21 November 2026. Closing date: 4 December 2026')[0]=='2026-12-04'
    assert extract_deadline('Auction advertised 21 November 2026')[0] is None
    assert extract_deadline('Deadline: 04/05/2026')[0] is None
    assert extract_deadline('Deadline: 4 December')[0] is None
    assert extract_deadline('Deadline: 4 December 2026\nClosing date: 8 December 2026')[0] is None


def test_classification_and_canonical():
    assert category('Public auction of motor vehicles')=='Auction'
    assert category('Call for proposals: enterprise grants')=='Grant'
    assert canonical('https://EXAMPLE.com/x?utm_source=test&id=5#top')=='https://example.com/x?id=5'


def test_feed_normalizes_discovery_links():
    class Response:
        content=b'''<rss version="2.0"><channel><item><title>Uganda business investment</title><link>https://www.bing.com/news/apiclick.aspx?url=https%3A%2F%2Fexample.com%2Fstory&amp;tid=changing</link><pubDate>Sat, 21 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>'''
    class Client:
        def get(self,url):return Response()
    rows,_=collect_feed(Client(),{'url':'https://example.com/feed','kind':'search','name':'News search'})
    assert rows[0]['url']=='https://example.com/story'
    assert rows[0]['published_at'].startswith('2026-11-21')
    assert rows[0].get('deadline') is None


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


def test_egp_pagination_and_explicit_deadline():
    class Response:
        content=b'<input name="_token" value="test">'
        def raise_for_status(self):pass
        def json(self):return {'recordsFiltered':26,'data':[{'action_links':'<a href="https://egpuganda.go.ug/index/one">View</a>','subject_procurement':'Supply of computers','submission_deadline':'2026-12-03','created_at':'2026-11-20T10:00:00Z'}]}
    class Client:
        def __init__(self):self.starts=[]
        def get(self,url):return Response()
        def request(self,url,method,data):self.starts.append(data['start']);return Response()
    c=Client();items,_=collect_egp(c,{'kind':'egp'})
    assert c.starts==[0,25]
    assert items[0]['deadline']=='2026-12-03' and items[0]['deadline_origin']=='official'


class JsonClient:
    """Fake HTTP client returning canned JSON per URL substring."""
    def __init__(self,routes):self.routes=routes;self.urls=[]
    def get(self,url):
        self.urls.append(url)
        payload=next(v for k,v in self.routes.items() if k in url)
        class Response:
            def json(self):return payload
        return Response()


def test_ppda_portal_uses_current_financial_year_and_official_deadline():
    from ugwatch.collectors import collect_ppda,financial_year
    from datetime import date
    assert financial_year(date(2026,11,22))=='2026-2027' and financial_year(date(2027,3,1))=='2026-2027'
    future=(datetime.now(EAT).date()+timedelta(days=9)).isoformat()
    c=JsonClient({
        'tender/notices/98737':{'success':True,'data':[{'procurement_reference_no':'NWSC-KW/SUPLS/2026-2027/1369742','procurement_method':'Open Domestic Bidding',
            'bid_security_amount':4000000,'bid_document_price':100000,'bid_openning_time':'11:00:00','bid_openning_address':'Plot 43/49 6th Street','bid_reciept_address':'Plot 43/49 6th Street'}]},
        'tender/notices?':{'success':True,'data':[
            {'id':98737,'title':'Supply of a lathe machine','estimatedValue':600000000,'procurement_type':'Supplies','entity':'NWSC','sector':'Water','deadline':future+' 00:00:00'},
            {'id':5,'title':'Closed supply tender','entity':'KCCA','deadline':'2020-01-01 00:00:00'},
            {'id':None,'title':'Broken row'}]}})
    items,message=collect_ppda(c,{'kind':'ppda'})
    assert 'fy=' in c.urls[0] and len(items)==2
    # Only the open notice triggers a detail request.
    assert c.urls[1:]==['https://cdn.ppda.go.ug/api/tender/notices/98737']
    row=items[0]
    assert row['url']=='https://gpp.ppda.go.ug/public/bid-invitations/tender-notice/98737'
    assert row['deadline']==future and row['deadline_origin']=='official' and row['category']=='Tender'
    assert row['organization']=='NWSC' and 'UGX 600,000,000' in row['excerpt'] and 'Open Domestic Bidding' in row['excerpt']
    assert row['reference']=='NWSC-KW/SUPLS/2026-2027/1369742'
    assert 'bids opened at 11:00' in row['deadline_evidence']
    assert items[1]['reference']=='' and '1 open notices enriched' in message


def test_transient_timeouts_are_retried_once():
    import requests
    from ugwatch.collectors import retrying
    calls=[]
    def flaky():
        calls.append(1)
        if len(calls)==1: raise requests.Timeout()
        return 'ok'
    assert retrying(flaky,pause=0)=='ok' and len(calls)==2
    def down(): raise requests.ConnectionError()
    with pytest.raises(requests.ConnectionError): retrying(down,pause=0)


def test_bou_reads_recent_documents_only():
    from ugwatch.collectors import collect_bou
    this_year=datetime.now(EAT).year
    doc=lambda title,url,desc='':{'title':title,'description':desc,'file':[{'url':url,'createdAt':'2026-11-10T08:26:09.960Z'}]}
    tree={'data':{'items':[
        {'category':'Bidding Documents','items':[
            {'year':str(this_year),'items':[{'month':'November','items':[doc('Provision of consultancy services','/uploads/a.pdf'),{'title':'No file','file':[]}]}]},
            {'year':str(this_year-5),'items':[{'month':'January','items':[doc('Old tender','/uploads/old.pdf')]}]}]},
        {'category':'Disposal','items':[{'year':str(this_year),'items':[{'month':'May','items':[doc('Disposal-of-vehi...','/uploads/b.pdf','Disposal-of-vehicles-at-Kampala')]}]}]}]}}
    items,_=collect_bou(JsonClient({'procurement':tree}),{'kind':'bou'})
    assert [i['url'] for i in items]==['https://bou.or.ug/uploads/a.pdf','https://bou.or.ug/uploads/b.pdf']
    assert items[0]['category']=='Tender' and items[1]['category']=='Auction'
    assert items[1]['title']=='Disposal of vehicles at Kampala'
    assert items[0]['published_at'].startswith('2026-11-10T11:26')


def test_newvision_generic_titles_and_extracted_deadline():
    from ugwatch.collectors import collect_newvision
    rows=[{'id':4096,'created_on':'2026-11-17 09:00:00','title':'ABRIDGED BID NOTICE','plain_text_description':'Bids for road works. Closing date: 4 December 2026.','tags':['new vision','uganda national roads authority','notice']},
          {'id':4090,'created_on':'2026-09-30 09:00:00','title':'How Mastercard is driving inclusion','plain_text_description':'A feature on finance.','tags':[]}]
    c=JsonClient({'Opportunities/Notices':rows})
    items,_=collect_newvision(c,{'kind':'newvision_notices'})
    first=items[0]
    assert first['url']=='https://www.newvision.co.ug/opportunities/notices-4096'
    assert first['title']=='Abridged Bid Notice: Uganda National Roads Authority'
    assert first['deadline']=='2026-12-04' and first['deadline_origin']=='extracted' and first['category']=='Bid'
    assert first['published_at']=='2026-11-17T09:00:00+03:00'
    assert items[1]['category']=='Public notice'


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


def test_blocked_site_gets_plain_message(monkeypatch):
    import requests
    from ugwatch import collectors
    def blocked(client,source):
        r=requests.Response();r.status_code=403
        raise requests.HTTPError(response=r)
    monkeypatch.setattr(collectors,'collect_html',blocked)
    with pytest.raises(ValueError,match='refused automated access'):
        collectors.collect({'kind':'html','url':'https://example.com'})


def test_current_view_hides_closed_stale_and_result_records(app,client):
    old=(datetime.now(EAT).date()-timedelta(days=120)).isoformat()
    insert(app)                                                                          # official, upcoming
    insert(app,url='https://example.com/fresh-undated',deadline=None,deadline_origin='listing')
    insert(app,url='https://example.com/stale-undated',deadline=None,deadline_origin='listing',published_at=old)
    insert(app,url='https://example.com/expired',deadline='2020-01-01')
    insert(app,url='https://example.com/beb',title='Best Evaluated Bidder Notice for cleaning services',deadline=None,deadline_origin='listing')
    insert(app,url='https://example.com/minutes',title='Bank tender',excerpt='Bank of Uganda · Prebid Minutes · May 2026',deadline=None,deadline_origin='listing')
    current=client.get('/api/notices?status=current').json
    assert {r['url'] for r in current['items']}=={'https://example.com/notice','https://example.com/fresh-undated'}
    assert current['hidden']==4
    assert client.get('/api/notices?status=results').json['total']==2
    assert client.get('/api/notices').json['total']==6 and client.get('/api/notices').json['hidden']==0
    assert client.get('/api/notices?status=review').json['total']==2   # stale undated still reviewable on request
    stats=client.get('/api/overview').json['stats']
    assert stats['current']==2 and stats['review']==1
    assert client.get('/api/notices?status=bogus').status_code==400


def test_reviewed_deadline_overrides_result_label(app,client):
    id=insert(app,url='https://example.com/award',title='Notice of award and re-tender',deadline=None,deadline_origin='listing')
    future=(datetime.now(EAT).date()+timedelta(days=5)).isoformat()
    client.patch(f'/api/notices/{id}',json={'user_deadline':future},headers={'X-CSRF-Token':client.csrf})
    row=client.get('/api/notices?status=current').json['items'][0]
    assert row['status']=='Upcoming'


def start_fake_run(app):
    from ugwatch.db import now
    with connect(app.config['DATABASE']) as db:
        return db.execute("INSERT INTO runs(started_at,state) VALUES (?,'complete')",(now(),)).lastrowid


def test_alerts_summarise_new_keyword_matches_only(app):
    from ugwatch.alerts import notify_run
    path=app.config['DATABASE']
    insert(app,url='https://example.com/old-match',title='Old computers tender')       # before the run: never re-alerted
    with connect(path) as db:
        db.execute("UPDATE notices SET first_seen='2000-01-01T00:00:00+03:00'")
        db.execute("INSERT INTO watchwords(term) VALUES ('computers')")
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
    assert client.get('/api/overview').json['settings']['alert_mode']=='matches'
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


def test_wordpress_cards_with_data_links():
    from ugwatch.collectors import collect_html
    html=b'''<html><body>
    <div class="w3eden"><div class="media-body"><h3 class="media-heading">Invitation to bid for photocopying and printing services</h3>
      <div class="text-small"><i></i> 195KB <i></i> Oct 02, 2026 <div class="mt-3"><a class="wpdm-download-link" href="#" data-downloadurl="https://era.example/download/itb-printing/?wpdmdl=1">Download</a></div></div></div></div>
    <table><tr data-href="https://uegcl.example/bids-and-tenders/hydraulic-truck/"><td><img alt=""></td>
      <td><h4 class="pub-title">Supply and Delivery of a Hydraulic Truck and Gate Control Spares</h4><p>The Entity invites sealed bids; grant funding applies.</p></td></tr>
      <tr data-href="https://uegcl.example/about/"><td><h4>About the company and its history</h4></td></tr></table>
    </body></html>'''
    class Response:
        content=html; url='https://era.example/procurement/'; headers={'Content-Type':'text/html'}
    class Client:
        def get(self,url):return Response()
    items,_=collect_html(Client(),{'name':'Test','url':'https://era.example/procurement/','kind':'html'})
    by_url={i['url']:i for i in items}
    era=by_url['https://era.example/download/itb-printing/?wpdmdl=1']
    assert era['title'].startswith('Invitation to bid') and era['published_at'].startswith('2026-10-02')
    truck=by_url['https://uegcl.example/bids-and-tenders/hydraulic-truck/']
    assert truck['category']=='Tender' and 'sealed bids' in truck['excerpt']
    assert 'https://uegcl.example/about/' not in by_url


def test_worldbank_notices_for_uganda():
    from ugwatch.collectors import collect_worldbank
    c=JsonClient({'procnotices':{'total':2,'procnotices':[
        {'id':'OP00482384','notice_type':'Invitation for Bids','noticedate':'19-Nov-2026','submission_deadline_date':'2026-12-03T00:00:00Z','submission_deadline_time':'11:00',
         'bid_description':'Supply of ICT equipment for government systems','contact_organization':'NITA-U','project_name':'Uganda Digital Acceleration Project','bid_reference_no':'UG-NITA-U-580461-GO-RFB','procurement_method_name':'Request for Bids'},
        {'id':'OP00482990','notice_type':'Contract Award','noticedate':'20-Nov-2026','submission_deadline_date':'2026-10-01T00:00:00Z','bid_description':'Printing services for school calendars'},
        {'id':'../bad','notice_type':'Invitation for Bids','bid_description':'Injected id'}]}})
    items,_=collect_worldbank(c,{'kind':'worldbank'})
    assert 'project_ctry_name_exact=Uganda' in c.urls[0] and len(items)==2
    bid,award=items
    assert bid['url'].endswith('/procurement-detail/OP00482384') and bid['deadline']=='2026-12-03' and bid['deadline_origin']=='official'
    assert '11:00 local time' in bid['deadline_evidence'] and bid['reference']=='UG-NITA-U-580461-GO-RFB' and bid['category']=='Tender'
    assert award['deadline'] is None and award['excerpt'].startswith('Contract Award') and award['published_at'].startswith('2026-11-20')


def test_worldbank_award_is_a_result(app,client):
    insert(app,url='https://projects.worldbank.org/x',title='Printing services',excerpt='Contract Award · Ministry',deadline=None,deadline_origin='feed')
    assert client.get('/api/notices?status=results').json['total']==1


def test_second_copy_detects_running_dashboard():
    import socket
    from run import already_running
    with socket.socket() as server:
        server.bind(('127.0.0.1',0)); server.listen(1)
        port=server.getsockname()[1]
        assert already_running(port)
    assert not already_running(port)


def test_client_retries_network_hiccups_and_busy_answers():
    import requests,socket
    from ugwatch.collectors import Client
    c=Client(); c.retry_waits=(0,0)
    calls=[]
    def flaky():
        calls.append(1)
        if len(calls)==1: raise requests.ConnectionError('reset')
        if len(calls)==2: raise socket.gaierror(11001,'getaddrinfo failed')
        return 'ok'
    assert c._retry(flaky)=='ok' and len(calls)==3
    class Busy:
        def __init__(self,code):self.status_code=code
        def close(self):pass
    answers=[Busy(503),Busy(200)]
    assert c._retry(lambda:answers.pop(0),lambda r:r.status_code in (502,503,504)).status_code==200
    def down(): raise requests.Timeout()
    with pytest.raises(requests.Timeout): c._retry(down)
    c.session.close()


def test_network_errors_are_temporary_blocks_are_not():
    import requests,socket
    from ugwatch.collectors import friendly_error,TemporaryError
    dns=friendly_error(socket.gaierror(11001,'getaddrinfo failed'))
    assert isinstance(dns,TemporaryError) and "look up the site's address" in str(dns)
    busy=requests.Response();busy.status_code=503
    assert isinstance(friendly_error(requests.HTTPError(response=busy)),TemporaryError)
    blocked=requests.Response();blocked.status_code=403
    err=friendly_error(requests.HTTPError(response=blocked))
    assert not isinstance(err,TemporaryError) and 'refused automated access' in str(err)
    assert isinstance(friendly_error(requests.ConnectionError('refused')),TemporaryError)


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


def test_only_one_copy_can_hold_the_app_lock(tmp_path):
    import subprocess,sys,textwrap
    from pathlib import Path
    from run import acquire_instance_lock
    lock=tmp_path/'app.lock'
    held=acquire_instance_lock(lock)
    assert held is not None
    probe=textwrap.dedent(f'''
        import sys; sys.path.insert(0,{str(Path(__file__).resolve().parent.parent)!r})
        from pathlib import Path
        from run import acquire_instance_lock
        print('free' if acquire_instance_lock(Path({str(lock)!r})) else 'taken')''')
    second=subprocess.run([sys.executable,'-c',probe],capture_output=True,text=True,timeout=60)
    assert second.stdout.strip()=='taken', second.stderr
    held.close()
    third=subprocess.run([sys.executable,'-c',probe],capture_output=True,text=True,timeout=60)
    assert third.stdout.strip()=='free', third.stderr


def test_second_server_cannot_share_the_port(app):
    from werkzeug.serving import make_server
    from run import exclusive_port_binding
    exclusive_port_binding()
    first=make_server('127.0.0.1',0,app)
    try:
        # Werkzeug reports the refused bind by exiting; either form means the port is protected.
        with pytest.raises((OSError,SystemExit)):
            make_server('127.0.0.1',first.server_port,app)
    finally:
        first.server_close()


MONITOR_PAGE=b'''<!DOCTYPE html><!-- saved from url=(0045)https://www.monitor.co.ug/uganda/jobs/tenders -->
<html><head><link rel="canonical" href="https://www.monitor.co.ug/uganda/jobs/tenders"></head><body>
<a href="/uganda/subscribe">Subscribe for a month to get full access</a>
<main><h2>TENDERS</h2>
<div><a href="https://www.monitor.co.ug/resource/blob/5677644/808a/ucu-eoi-data.pdf"><h3>UGANDA CHRISTIAN UNIVERSITY (UCU) - REQUEST FOR EXPRESSION OF INTEREST: CAMPUS TRANSFORMATION</h3></a>
<p>Uganda Christian University invites real estate developers to express interest in a Finance, Build, Operate and Transfer project.</p></div>
<div><a href="https://www.monitor.co.ug/resource/blob/5566040/d4e2/good-neighbors-data.pdf"><h3>GOOD NEIGHBORS INTERNATIONAL UGANDA: MIDLINE SURVEY CONSULTANCY OPPORTUNITY</h3></a><p>Consultants are invited.</p></div>
<div><a href="https://www.monitor.co.ug/resource/blob/5631590/f5ff/syova-data.pdf"><h3>SYOVA SEED (U) LTD. - 64TH INDEPENDENCE ANNIVERSARY CELEBRATIONS</h3></a></div>
<div><a href="mailto:procurement@example.org"><h3>procurement@example.org is the contact address here</h3></a></div>
</main></body></html>'''


def test_saved_monitor_page_parsing():
    from ugwatch.collectors import parse_listing
    items=parse_listing(MONITOR_PAGE,'https://www.monitor.co.ug/uganda/jobs/tenders',{'name':'Daily Monitor • tenders','kind':'import_tenders'})
    titles=[i['title'] for i in items]
    assert len(items)==2 and titles[0].startswith('UGANDA CHRISTIAN UNIVERSITY')
    assert items[0]['category']=='Tender' and 'Finance, Build, Operate' in items[0]['excerpt']
    assert items[1]['category']=='Tender'                                         # no keyword, but on the tenders page
    assert not any('Subscribe' in t or 'ANNIVERSARY' in t for t in titles)


def test_upload_month_dates_old_wordpress_documents():
    from ugwatch.collectors import upload_date
    assert upload_date('https://x.go.ug/wp-content/uploads/2020/07/Bid-Notice.pdf')=='2020-07-01T00:00:00+03:00'
    assert upload_date('https://x.go.ug/tenders/supply-of-vehicles/') is None


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


def insert_job(app,url,title,**extra):
    return insert(app,**{'url':url,'title':title,'category':'Job','deadline':None,'deadline_origin':'feed',**extra})


def test_jobs_have_their_own_page_and_stay_out_of_tenders(app,client):
    insert(app)                                                                          # a tender
    insert_job(app,'https://jobs.example/acc','Accountant at Hima Cement Ltd',organization='Hima Cement Ltd')
    assert client.get('/api/notices').json['total']==1
    assert client.get('/api/notices?status=current').json['items'][0]['category']=='Tender'
    jobs=client.get('/api/notices?view=jobs&status=current').json
    assert jobs['total']==1 and jobs['items'][0]['status']=='Open'
    stats=client.get('/api/overview').json['stats']
    assert stats['total']==1 and stats['jobs_open']==1


def test_job_keywords_rank_filter_and_search(app,client):
    h={'X-CSRF-Token':client.csrf}
    insert_job(app,'https://jobs.example/1','Driver at Kampala Logistics')
    insert_job(app,'https://jobs.example/2','ICT Officer at Gulu University',excerpt='Network and ICT support in Gulu')
    insert_job(app,'https://jobs.example/3','Accountant at Gulu Hospital')
    for term in ('ICT','Gulu'): assert client.post('/api/jobwords',json={'term':term},headers=h).status_code==201
    ranked=client.get('/api/notices?view=jobs&sort=match').json['items']
    assert [r['url'][-1] for r in ranked][:2]==['2','3'] and sorted(ranked[0]['job_matches'])==['Gulu','ICT']
    mine=client.get('/api/notices?view=jobs&mine=1').json
    assert mine['total']==2
    assert client.get('/api/notices?view=jobs&q=driver').json['total']==1
    words=client.get('/api/overview').json['job_words']
    assert sorted(w['term'] for w in words)==['Gulu','ICT']
    client.delete(f"/api/jobwords/{words[0]['id']}",headers=h)
    assert len(client.get('/api/overview').json['job_words'])==1
    assert client.post('/api/jobwords',json={'term':''},headers=h).status_code==400


def test_job_closing_dates_and_old_posts(app,client):
    today=datetime.now(EAT).date()
    insert_job(app,'https://jobs.example/closed','Nurse at Mulago',deadline=(today-timedelta(days=1)).isoformat(),deadline_origin='extracted')
    insert_job(app,'https://jobs.example/open','Engineer at UEGCL',deadline=(today+timedelta(days=5)).isoformat(),deadline_origin='extracted')
    insert_job(app,'https://jobs.example/old','Clerk at Old Co',published_at=(today-timedelta(days=90)).isoformat())
    insert_job(app,'https://jobs.example/live','Cashier at Shop',baseline=True)            # undated, still on the board
    insert_job(app,'https://jobs.example/gone','Guard at Firm')
    with connect(app.config['DATABASE']) as db:
        db.execute("UPDATE notices SET last_seen='2026-01-01T00:00:00+03:00' WHERE url='https://jobs.example/gone'")
    by={r['url'][-4:]:r['status'] for r in client.get('/api/notices?view=jobs').json['items']}
    assert by=={'osed':'Closed','open':'Open','/old':'Older post','live':'Open','gone':'No longer listed'}
    cur=client.get('/api/notices?view=jobs&status=current').json
    assert cur['total']==2 and cur['hidden']==3


def test_job_feed_and_listing_readers():
    from ugwatch.collectors import collect_jobs_feed,collect_job_listing,job_organization
    assert job_organization('Accountant  at HR Consults Uganda')=='HR Consults Uganda'
    assert job_organization('Barista job at Bulungi Town')=='Bulungi Town'
    feed=b'''<rss version="2.0"><channel><item><title>Brand Coordinator at CFAO Mobility</title><link>https://jobweb.example/jobs/brand-coordinator/</link>
      <pubDate>Thu, 19 Nov 2026 06:12:51 +0000</pubDate><description>Reports to marketing. Deadline: 30 November 2026.</description></item></channel></rss>'''
    class Resp:
        def __init__(self,content,url='https://www.brightermonday.co.ug/jobs'):self.content=content;self.url=url
    class FeedClient:
        def __init__(self):self.urls=[]
        def get(self,url):
            self.urls.append(url)
            return Resp(feed if 'paged' not in url else b'<rss version="2.0"><channel></channel></rss>')
    c=FeedClient(); items,_=collect_jobs_feed(c,{'name':'Jobweb','url':'https://jobweb.example/feed/?post_type=job_listing'})
    assert c.urls[1].endswith('&paged=2') and len(items)==1
    job=items[0]
    assert job['category']=='Job' and job['organization']=='CFAO Mobility' and job['deadline']=='2026-11-30' and job['published_at'].startswith('2026-11-19')
    page=b'''<html><body><nav><a href="/jobs/accounting">Accounting jobs (25)</a></nav>
      <div class="card"><a href="/listings/quality-manager-7wk7dx">Quality Manager</a><p>S  SMARTEC ELECTRONICS LTD New (posted Today) Health &amp; safety - ensure services meet contracts.</p><a href="/listings/quality-manager-7wk7dx">Apply</a></div>
      <a href="/listings/accounting">Accounting, Auditing &amp; Finance (25)</a></body></html>'''
    class PageClient:
        def get(self,url):return Resp(page)
    items,_=collect_job_listing(PageClient(),{'name':'BrighterMonday','url':'https://www.brightermonday.co.ug/jobs'})
    assert [i['title'] for i in items]==['Quality Manager']
    assert items[0]['organization']=='SMARTEC ELECTRONICS LTD' and items[0]['excerpt'].startswith('SMARTEC')


def test_jobs_never_trigger_tender_alerts(app):
    from ugwatch.alerts import notify_run
    path=app.config['DATABASE']
    with connect(path) as db:
        db.execute("UPDATE settings SET value='open' WHERE key='alert_mode'")
        db.execute("INSERT INTO watchwords(term) VALUES ('accountant')")
    run_id=start_fake_run(app)
    insert_job(app,'https://jobs.example/acc2','Accountant at Bank',deadline=(datetime.now(EAT).date()+timedelta(days=3)).isoformat(),deadline_origin='official')
    sent=[]
    assert notify_run(path,run_id,sender=lambda *a:(sent.append(a),(True,'ok'))[1])==0 and not sent
