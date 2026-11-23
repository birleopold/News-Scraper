import pytest
from datetime import datetime,timedelta
from ugwatch.db import connect,upsert_notice,EAT
from ugwatch.collectors import extract_deadline,canonical,category,public_url,collect_feed,collect_egp
from ugwatch import service
from helpers import insert,JsonClient,start_fake_run,insert_job,MONITOR_PAGE


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


def test_worldbank_award_is_a_result(app,client):
    insert(app,url='https://projects.worldbank.org/x',title='Printing services',excerpt='Contract Award · Ministry',deadline=None,deadline_origin='feed')
    assert client.get('/api/notices?status=results').json['total']==1
