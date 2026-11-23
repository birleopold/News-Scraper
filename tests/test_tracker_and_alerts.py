"""Scanned adverts, the hourly disposal check, bid tracker, calendar, smarter alerts,
reminders and the archive."""
import json
from datetime import datetime, timedelta

from ugwatch import service
from ugwatch.db import EAT, connect
from helpers import insert, start_fake_run

TODAY = datetime.now(EAT).date()
ADVERT = ('DISPOSAL NOTICE. Bids are invited for the purchase of used motor vehicles at Gulu. '
          'Viewing will be on 1st December 2026. The auction will take place on 12th December 2026.')


def sale(app, key, title, **extra):
    return insert(app, **{'url': f'https://x.example/{key}', 'title': title, 'category': 'Auction',
                          'deadline': None, 'deadline_origin': 'listing', **extra})


def test_scanned_adverts_are_read_with_ocr(app, monkeypatch):
    from ugwatch import enrich, ocr
    insert(app, url='https://nv.example/notices-9', title='PUBLIC NOTICE', category='Public notice', deadline=None,
           deadline_origin='listing', pdf_url='https://media.example/scan.pdf')
    monkeypatch.setattr(enrich, 'pdf_text', lambda content: '')            # a picture only
    monkeypatch.setattr(ocr, 'available', lambda: True)
    monkeypatch.setattr(ocr, 'ocr_pdf', lambda content: ADVERT + ' ' + 'word ' * 30)

    class Client:
        def get(self, url):
            class R: content = b'%PDF'
            return R()
    assert enrich.enrich(app.config['DATABASE'], client=Client()) == 1
    with connect(app.config['DATABASE']) as db:
        row = db.execute("SELECT category,details FROM notices WHERE url LIKE '%notices-9'").fetchone()
    facts = json.loads(row['details'])
    assert row['category'] == 'Auction' and facts['ocr'] is True and facts['ocr_tried'] is True
    assert facts['viewing'] == '2026-12-01' and facts['auction_date'] == '2026-12-12' and 'scanned' not in facts


def test_hourly_check_reads_only_egp_disposals(app, monkeypatch):
    seen = []
    monkeypatch.setattr(service, 'collect', lambda s: (seen.append(s['kind']), ([], 'ok'))[1])
    service.start_run(app.config['DATABASE'], background=False, scope='disposals')
    assert seen == ['egp_disposal']
    with connect(app.config['DATABASE']) as db:
        run = db.execute('SELECT scope,message FROM runs').fetchone()
    assert run['scope'] == 'disposals' and run['message'].startswith('Hourly disposal check')


def test_bid_tracker_saves_validates_and_filters(app, client):
    h = {'X-CSRF-Token': client.csrf}
    a = sale(app, 'a', 'Disposal of used vehicles at Gulu')
    sale(app, 'b', 'Auction of scrap metal at Jinja')
    assert client.patch(f'/api/notices/{a}', json={'pipeline': 'bid', 'my_bid': '12,500,000'}, headers=h).status_code == 200
    assert client.patch(f'/api/notices/{a}', json={'pipeline': 'maybe'}, headers=h).status_code == 400
    assert client.patch(f'/api/notices/{a}', json={'my_bid': 'lots'}, headers=h).status_code == 400
    assert client.patch(f'/api/notices/{a}', json={'my_bid': -5}, headers=h).status_code == 400
    mine = client.get('/api/notices?view=disposals&pipeline=any').json['items']
    assert [(i['url'][-1], i['pipeline'], i['my_bid']) for i in mine] == [('a', 'bid', 12500000)]
    assert client.get('/api/notices?view=disposals&pipeline=won').json['total'] == 0
    client.patch(f'/api/notices/{a}', json={'pipeline': 'lost', 'outcome_amount': 14000000, 'my_bid': None}, headers=h)
    item = client.get('/api/notices?view=disposals&pipeline=lost').json['items'][0]
    assert (item['my_bid'], item['outcome_amount']) == (None, 14000000)


def test_your_past_bids_lead_the_price_history(app, client):
    h = {'X-CSRF-Token': client.csrf}
    new = sale(app, 'new', 'Disposal of motor vehicles at Lira', organization='Ministry A')
    old = sale(app, 'old', 'Disposal of vehicles in Gulu', organization='Ministry B')
    sale(app, 'same', 'Disposal of vehicles at Mbale', organization='Ministry A')
    client.patch(f'/api/notices/{old}', json={'pipeline': 'won', 'my_bid': 9000000, 'outcome_amount': 9000000}, headers=h)
    history = client.get(f'/api/notices/{new}/history').json['items']
    assert history[0]['url'].endswith('/old') and history[0]['my_bid'] == 9000000 and history[0]['pipeline'] == 'won'


def test_calendar_files(app, client):
    h = {'X-CSRF-Token': client.csrf}
    a = sale(app, 'cal', 'Disposal of vehicles; Gulu, Lira', deadline=(TODAY + timedelta(days=9)).isoformat(), deadline_origin='official')
    with connect(app.config['DATABASE']) as db:
        db.execute('UPDATE notices SET details=? WHERE id=?', (json.dumps({'viewing': '2026-12-01', 'auction_date': '2026-12-12'}), a))
    r = client.get(f'/api/notices/{a}/calendar.ics')
    text = r.get_data(as_text=True)
    assert r.status_code == 200 and r.mimetype == 'text/calendar' and text.count('BEGIN:VEVENT') == 3
    assert 'DTSTART;VALUE=DATE:20261201' in text and 'Disposal of vehicles\\; Gulu\\, Lira' in text
    assert all(len(line.encode()) <= 75 for line in text.split('\r\n'))
    empty = client.get('/api/calendar.ics')                                       # nothing tracked or saved yet
    assert empty.status_code == 200 and 'BEGIN:VCALENDAR' in empty.get_data(as_text=True) and 'VEVENT' not in empty.get_data(as_text=True)
    client.patch(f'/api/notices/{a}', json={'pipeline': 'interested'}, headers=h)
    assert client.get('/api/calendar.ics').get_data(as_text=True).count('BEGIN:VEVENT') == 3


def test_disposal_alerts_follow_asset_and_place_choices(app, client):
    from ugwatch.alerts import notify_run
    h = {'X-CSRF-Token': client.csrf}
    assert client.patch('/api/alerts', json={'mode': 'disposals', 'assets': ['Vehicles'], 'places': ['Kampala', 'Wakiso']}, headers=h).status_code == 200
    assert client.patch('/api/alerts', json={'mode': 'disposals', 'assets': ['Boats']}, headers=h).status_code == 400
    assert client.patch('/api/alerts', json={'mode': 'disposals', 'places': ['Atlantis']}, headers=h).status_code == 400
    run_id = start_fake_run(app)
    sale(app, 'want', 'Disposal of motor vehicles at Kampala')
    sale(app, 'wrongplace', 'Disposal of motor vehicles at Gulu')
    sale(app, 'wrongasset', 'Auction of scrap metal at Kampala')
    sale(app, 'unknown', 'Public auction notice')                                   # nothing readable: still alerted
    sent = []
    assert notify_run(app.config['DATABASE'], run_id, sender=lambda *a: (sent.append(a), (True, 'ok'))[1]) == 2
    assert 'Kampala' in sent[0][1] and 'Gulu' not in sent[0][1] and 'scrap' not in sent[0][1]


def test_date_reminders_are_sent_once_and_monitor_weekly(app, client, monkeypatch):
    from ugwatch import alerts
    from ugwatch.alerts import send_reminders
    monkeypatch.setattr(alerts, 'REMINDER_HOUR', 0)                                  # independent of the time the tests run
    h = {'X-CSRF-Token': client.csrf}
    path = app.config['DATABASE']
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    tracked = sale(app, 'tracked', 'Disposal of tractors', deadline=tomorrow, deadline_origin='official')
    sale(app, 'untracked', 'Disposal of pigs', deadline=tomorrow, deadline_origin='official')
    with connect(path) as db:
        db.execute('UPDATE notices SET details=? WHERE id=?', (json.dumps({'viewing': TODAY.isoformat()}), tracked))
    client.patch(f'/api/notices/{tracked}', json={'pipeline': 'interested'}, headers=h)
    sent = []
    sender = lambda *a: (sent.append(a), (True, 'ok'))[1]
    assert send_reminders(path, sender=sender, today=TODAY) == 2                     # the dates + "import Daily Monitor"
    dates = next(s for s in sent if 'coming up' in s[0])
    assert dates[0] == '2 dates coming up' and 'Viewing today' in dates[1] and 'Closes tomorrow' in dates[1] and 'pigs' not in dates[1]
    assert any(s[0] == 'Time to import Daily Monitor' and s[2].endswith('?view=sources') for s in sent)
    sent.clear()
    assert send_reminders(path, sender=sender, today=TODAY) == 0 and not sent       # each date once; Monitor weekly
    with connect(path) as db: db.execute("UPDATE settings SET value='off' WHERE key='alert_mode'")
    with connect(path) as db: db.execute("UPDATE notices SET reminded=''")
    assert send_reminders(path, sender=sender, today=TODAY) == 0                     # alerts off: no reminders


def test_old_records_are_archived_but_searchable(app, client):
    old = (TODAY - timedelta(days=900)).isoformat()
    sale(app, 'ancient', 'Disposal of typewriters', published_at=old)
    saved = sale(app, 'kept', 'Disposal of old radios', published_at=old)
    client.patch(f'/api/notices/{saved}', json={'saved': True}, headers={'X-CSRF-Token': client.csrf})
    sale(app, 'fresh', 'Disposal of laptops')
    listing = client.get('/api/notices?view=disposals').json
    assert sorted(i['url'][-4:] for i in listing['items']) == ['kept', 'resh'] and listing['archived'] == 1
    assert client.get('/api/notices?view=disposals&archived=1').json['total'] == 3
    assert client.get('/api/notices?q=typewriters').json['total'] == 1             # search reaches the archive
