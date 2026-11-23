"""Shared test helpers: insert notices and fake HTTP clients."""
from datetime import datetime,timedelta
from ugwatch.db import connect,upsert_notice,EAT


def insert(app,**overrides):
    item=dict(url='https://example.com/notice',title='Tender for office computers',category='Tender',deadline_origin='official',deadline=(datetime.now(EAT).date()+timedelta(days=3)).isoformat())
    item.update(overrides)
    with connect(app.config['DATABASE']) as db:
        upsert_notice(db,1,item)
        return db.execute('SELECT id FROM notices WHERE url=?',(item['url'],)).fetchone()['id']


class JsonClient:
    """Fake HTTP client returning canned JSON per URL substring."""
    def __init__(self,routes):self.routes=routes;self.urls=[]
    def get(self,url):
        self.urls.append(url)
        payload=next(v for k,v in self.routes.items() if k in url)
        class Response:
            def json(self):return payload
        return Response()


def start_fake_run(app):
    from ugwatch.db import now
    with connect(app.config['DATABASE']) as db:
        return db.execute("INSERT INTO runs(started_at,state) VALUES (?,'complete')",(now(),)).lastrowid


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


def insert_job(app,url,title,**extra):
    return insert(app,**{'url':url,'title':title,'category':'Job','deadline':None,'deadline_origin':'feed',**extra})
