"""Disposal advert PDFs, classification fixes, filters, price history and duplicates."""
import json

import pytest
import requests

from ugwatch.db import connect, upsert_notice
from helpers import insert

ADVERT = ('UGANDA REVENUE AUTHORITY Plot M193/4 Nakawa Industrial Area Road, P.O. Box 7279, Kampala. '
          'ABRIDGED DISPOSAL NOTICE. The Authority invites bids for the purchase of boarded-off motor vehicles '
          'and scrap at its Jinja and Mbale stations, in accordance with the Public Procurement and Disposal of Public Assets Act. '
          'Lot 1: Toyota Land Cruiser. Lot 2: Isuzu truck. Lot 3: Assorted scrap metal. '
          'Viewing of the items will be on 1st December 2026. Bid security of UGX 500,000 is required. '
          'Bids must be submitted by 10th December 2026. The auction will take place on 12th December 2026.')


def test_procurement_law_boilerplate_and_treasury_auctions_are_not_disposals():
    from ugwatch.classify import is_asset_disposal
    assert not is_asset_disposal('Hire of warehouse, in accordance with the Public Procurement and Disposal of Public Assets Act, 2003')
    assert not is_asset_disposal('Documents are issued at the Procurement & Disposal Department, National Medical Stores')
    assert not is_asset_disposal('AUCTION INVITATION Bank of Uganda invites applications for Uganda Government Treasury Bonds')
    assert is_asset_disposal('DISPOSAL OF USED EQUIPMENTS. Bids are invited in accordance with the PPDA Act')


def test_facts_are_read_from_the_sale_wording_not_the_letterhead():
    from ugwatch.enrich import advert_details, summary_line
    d = advert_details(ADVERT, 'ABRIDGED DISPOSAL NOTICE')
    assert set(d['assets']) == {'Vehicles', 'Scrap & metal'}          # not "Land & buildings" from "Plot M193/4 ..."
    assert d['places'] == ['Jinja', 'Mbale']                            # not Kampala from the P.O. Box
    assert (d['viewing'], d['auction_date'], d['deadline']) == ('2026-12-01', '2026-12-12', '2026-12-10')
    assert d['bid_security'] == 500000 and d['lots'] == 3
    assert 'viewing 01 Dec 2026' in summary_line(d)


class PdfClient:
    """Fake client: each URL maps to bytes, or to an exception to raise."""
    def __init__(self, pages): self.pages = pages
    def get(self, url):
        value = self.pages[url]
        if isinstance(value, Exception): raise value
        class R: content = value
        return R()


def test_reading_advert_pdfs_finds_hidden_disposals(app, client, monkeypatch):
    from ugwatch import enrich
    path = app.config['DATABASE']
    for n, pdf in (('1', '1.pdf'), ('2', 'scan.pdf'), ('3', 'offline.pdf')):
        insert(app, url=f'https://nv.example/notices-{n}', title='PUBLIC NOTICE', category='Public notice', deadline=None,
               deadline_origin='listing', excerpt='See advert', pdf_url=f'https://media.example/{pdf}')
    monkeypatch.setattr(enrich, 'pdf_text', lambda content: content.decode())
    fake = PdfClient({'https://media.example/1.pdf': ADVERT.encode(), 'https://media.example/scan.pdf': b'   ',
                      'https://media.example/offline.pdf': requests.ConnectionError('down')})
    assert enrich.enrich(path, client=fake) == 2                         # the offline one is retried next time
    with connect(path) as db:
        rows = {r['url'][-1]: dict(r) for r in db.execute('SELECT * FROM notices')}
    sale = rows['1']
    assert sale['category'] == 'Auction' and sale['excerpt'] == 'See advert'   # excerpt is never rewritten
    assert sale['deadline'] == '2026-12-10' and sale['deadline_origin'] == 'extracted'
    assert json.loads(rows['2']['details'])['scanned'] is True
    assert rows['3']['details'] is None
    item = next(i for i in client.get('/api/notices?view=disposals').json['items'] if i['url'].endswith('-1'))
    assert item['facts']['bid_security'] == 500000 and 'text' not in item['facts'] and 'details' not in item
    assert set(item['assets']) == {'Vehicles', 'Scrap & metal'}


def test_stored_false_disposals_are_reclassified(app):
    from ugwatch.enrich import reclassify
    insert(app, url='https://x.example/warehouse', title='Hire of warehouse', category='Auction',
           excerpt='Per the Public Procurement and Disposal of Public Assets Act')
    insert(app, url='https://x.example/sale', title='Sale of used vehicles', category='Tender')
    with connect(app.config['DATABASE']) as db:
        assert reclassify(db) == 2
        cats = {r['url'][-4:]: r['category'] for r in db.execute('SELECT url,category FROM notices')}
    assert cats == {'ouse': 'Tender', 'sale': 'Auction'}


def test_disposal_filters_and_price_history(app, client):
    ids = {}
    for key, title, org in [('a', 'Disposal of used motor vehicles at Gulu', 'Uganda Police'),
                            ('b', 'Disposal of boarded-off vehicles in Lira', 'Uganda Police'),
                            ('c', 'Auction of scrap metal at Jinja', 'NWSC'), ('d', 'Sale of land in Mbarara', 'Bank X')]:
        ids[key] = insert(app, url=f'https://x.example/{key}', title=title, category='Auction', organization=org,
                          deadline=None, deadline_origin='listing')
    facets = client.get('/api/overview').json['disposal_facets']
    assert {f['name']: f['count'] for f in facets['assets']} == {'Vehicles': 2, 'Scrap & metal': 1, 'Land & buildings': 1}
    assert client.get('/api/notices?view=disposals&asset=Vehicles').json['total'] == 2
    assert [i['url'][-1] for i in client.get('/api/notices?view=disposals&place=Jinja').json['items']] == ['c']
    history = client.get(f"/api/notices/{ids['a']}/history").json['items']
    assert [h['url'][-1] for h in history] == ['b']                     # same seller and asset type; the rest unrelated
    assert client.get('/api/notices/99999/history').status_code == 404


def test_same_advert_on_two_sources_is_shown_once(app, client):
    with connect(app.config['DATABASE']) as db:
        db.execute("INSERT INTO sources(name,url,kind,group_name) VALUES ('Second paper','https://two.example','html','Newspapers')")
        second = db.execute("SELECT id FROM sources WHERE name='Second paper'").fetchone()[0]
        upsert_notice(db, 1, dict(url='https://one.example/a', title='Disposal of Boarded-off Motor Vehicles at Gulu Barracks',
                                  category='Auction', deadline_origin='official', deadline='2030-01-05'))
        upsert_notice(db, second, dict(url='https://two.example/a', title='DISPOSAL OF BOARDED OFF MOTOR VEHICLES - GULU BARRACKS',
                                       category='Auction', deadline_origin='listing'))
        upsert_notice(db, second, dict(url='https://two.example/b', title='PUBLIC NOTICE', category='Auction', deadline_origin='listing'))
        upsert_notice(db, 1, dict(url='https://one.example/c', title='PUBLIC NOTICE', category='Auction', deadline_origin='listing'))
    items = client.get('/api/notices?view=disposals').json['items']
    kept = [i for i in items if 'Gulu' in i['title'].title()]
    assert len(kept) == 1 and kept[0]['url'] == 'https://one.example/a'     # the official copy is kept
    assert kept[0]['also_at'] == [{'source': 'Second paper', 'url': 'https://two.example/a'}]
    assert sum(i['title'] == 'PUBLIC NOTICE' for i in items) == 2           # vague titles are never merged
    assert client.get('/api/notices?view=disposals&dupes=1').json['total'] == 4


def test_missing_robots_file_follows_rfc_9309(monkeypatch):
    from ugwatch import collectors
    monkeypatch.setattr(collectors, 'public_url', lambda url: url)

    class Answer:
        def __init__(self, code, body): self.status_code, self.content, self.headers = code, body, {}
        is_redirect = False
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def close(self): pass
        def iter_content(self, size): return iter([self.content])
        @property
        def text(self): return self.content.decode()
        def raise_for_status(self):
            if self.status_code >= 400:
                error = requests.HTTPError(f'{self.status_code} error'); error.response = self; raise error

    codes = {'https://s3.example/robots.txt': 403, 'https://busy.example/robots.txt': 503}
    c = collectors.Client(); c.retry_waits = ()
    monkeypatch.setattr(c.session, 'request', lambda method, url, **kw: Answer(codes.get(url, 200), b'%PDF advert'))
    assert c.get('https://s3.example/advert.pdf').content == b'%PDF advert'   # 403 robots.txt = no robots file
    with pytest.raises(requests.HTTPError): c.get('https://busy.example/page')  # 5xx robots.txt = stay away
