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
