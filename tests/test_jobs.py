import pytest
from datetime import datetime,timedelta
from ugwatch.db import connect,upsert_notice,EAT
from ugwatch.collectors import extract_deadline,canonical,category,public_url,collect_feed,collect_egp
from ugwatch import service
from helpers import insert,JsonClient,start_fake_run,insert_job,MONITOR_PAGE


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
