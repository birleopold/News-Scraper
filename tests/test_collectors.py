import pytest
from datetime import datetime,timedelta
from ugwatch.db import connect,upsert_notice,EAT
from ugwatch.collectors import extract_deadline,canonical,category,public_url,collect_feed,collect_egp
from ugwatch import service
from helpers import insert,JsonClient,start_fake_run,insert_job,MONITOR_PAGE


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


def test_blocked_site_gets_plain_message(monkeypatch):
    import requests
    from ugwatch import collectors
    def blocked(client,source):
        r=requests.Response();r.status_code=403
        raise requests.HTTPError(response=r)
    monkeypatch.setattr(collectors,'collect_html',blocked)
    with pytest.raises(ValueError,match='refused automated access'):
        collectors.collect({'kind':'html','url':'https://example.com'})


def test_upload_month_dates_old_wordpress_documents():
    from ugwatch.collectors import upload_date
    assert upload_date('https://x.go.ug/wp-content/uploads/2020/07/Bid-Notice.pdf')=='2020-07-01T00:00:00+03:00'
    assert upload_date('https://x.go.ug/tenders/supply-of-vehicles/') is None
