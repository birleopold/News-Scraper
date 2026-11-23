"""Read disposal advert PDFs for what is sold, where, and when; keep categories honest.

Disposal adverts usually say little in their headline ("PUBLIC NOTICE"); the PDF has
the assets, location, viewing dates, auction or closing date and bid security. Only a
few PDFs are read per fetch, each once, through the normal polite client.
"""
import json
import logging
import re
from datetime import datetime
from io import BytesIO

from dateutil import parser as dateparser
import requests
from pypdf import PdfReader

from .classify import ADDRESS, ASSET_DISPOSAL, BOILERPLATE, asset_types, category, is_asset_disposal, places
from .collectors import DATE_RX, Client, TemporaryError, clean, extract_deadline
from .db import EAT, connect

log = logging.getLogger(__name__)
PDF_PAGES = 5      # adverts and the key facts of bidding documents are on the first pages
PER_RUN = 15
GENERIC_TITLE = re.compile(r'^(?:abridged |detailed )?(?:public notice|notice|tender notice|bid notice|bid announcement|'
                           r'invitation to (?:tender|bid)|procurement notice|scheduled auction.*|auction invitation)\b.{0,40}$',re.I)
MONEY = re.compile(r'(?:UGX|U\.?\s?Shs?\.?|Shs\.?|Ushs\.?)\s?([\d][\d,]{3,}(?:\.\d+)?)(?:\s?(?:/=|=/))?',re.I)


def _date(text, labels):
    m = re.search(r'(?:' + labels + r')[^.\n]{0,80}?(' + DATE_RX + r')', text, re.I)
    if not m: return None
    raw = re.sub(r'(\d)(st|nd|rd|th)', r'\1', m.group(1), flags=re.I)
    try: return dateparser.parse(raw).date().isoformat()
    except (ValueError, OverflowError): return None


def amounts(text):
    out = []
    for m in MONEY.finditer(text):
        try: value = int(float(m.group(1).replace(',', '')))
        except ValueError: continue
        if value >= 1000: out.append(value)
    return out


def sale_passages(text, title=''):
    """The parts of an advert that describe what is sold: text around disposal/auction
    wording. Letterheads and bidding-document boilerplate mention addresses and
    "premises" that would otherwise read as assets and places."""
    plain = ADDRESS.sub(' ', BOILERPLATE.sub(' ', text))
    spans = [(max(0, m.start() - 300), m.end() + 600) for m in ASSET_DISPOSAL.finditer(plain)][:8]
    if not spans: return title + ' ' + plain[:1500]
    return title + ' ' + ' … '.join(plain[a:b] for a, b in spans)[:5000]


def advert_details(text, title=''):
    """Structured facts from an advert's text. Everything is 'as stated in the advert'."""
    text = clean(text)
    passages = sale_passages(text, title)
    security = re.search(r'bid security[^.\n]{0,80}?' + MONEY.pattern, text, re.I)
    lots = {m.group(1) for m in re.finditer(r'\blot\s*(?:no\.?\s*)?(\d{1,3})\b', passages, re.I)}
    deadline, evidence = extract_deadline(text)
    return {
        'assets': asset_types(passages),
        'places': places(passages)[:6],
        'viewing': _date(text, r'view(?:ing)?|inspection|inspect'),
        'auction_date': _date(text, r'auction (?:will (?:be held|take place)|is scheduled|scheduled|date)|scheduled to take place on|take place on'),
        'deadline': deadline, 'deadline_evidence': evidence,
        'bid_security': int(float(security.group(1).replace(',', ''))) if security else None,
        'amounts': sorted(set(amounts(text)))[:20],
        'lots': len(lots) or None,
        'chars': len(text),
    }


def pdf_text(content):
    reader = PdfReader(BytesIO(content))
    return '\n'.join((page.extract_text() or '') for page in reader.pages[:PDF_PAGES])


def summary_line(details):
    parts = []
    if details.get('assets'): parts.append(', '.join(details['assets']))
    if details.get('lots'): parts.append(f"{details['lots']} lots")
    if details.get('places'): parts.append(' / '.join(details['places'][:3]))
    if details.get('viewing'): parts.append('viewing ' + datetime.fromisoformat(details['viewing']).strftime('%d %b %Y'))
    if details.get('auction_date'): parts.append('auction ' + datetime.fromisoformat(details['auction_date']).strftime('%d %b %Y'))
    if details.get('bid_security'): parts.append(f"bid security UGX {details['bid_security']:,}")
    return ' · '.join(parts)


def reclassify(db):
    """Re-check stored categories with the current rules (e.g. after fixing a false positive)."""
    changed = 0
    for row in db.execute("SELECT id,title,excerpt,category,details FROM notices WHERE category NOT IN ('Job')").fetchall():
        text = row['title'] + ' ' + (row['excerpt'] or '')[:600]
        if row['details']:
            try: text += ' ' + (json.loads(row['details']).get('text') or '')[:1500]
            except ValueError: pass
        sale = is_asset_disposal(text)
        if row['category'] == 'Auction' and not sale:
            new = category(text) or 'Tender'
        elif row['category'] != 'Auction' and sale:
            new = 'Auction'
        else:
            continue
        db.execute('UPDATE notices SET category=? WHERE id=?', (new, row['id']))
        changed += 1
    return changed


def candidates(db, limit):
    """Disposals with an unread PDF first, then vaguely titled newspaper notices that may hide one."""
    rows = db.execute("""SELECT n.id,n.title,n.url,n.pdf_url,n.category,n.deadline,n.deadline_origin,n.excerpt FROM notices n
                         WHERE n.details IS NULL AND n.category!='Job'
                           AND (n.pdf_url IS NOT NULL OR lower(n.url) LIKE '%.pdf')
                         ORDER BY n.category='Auction' DESC, n.first_seen DESC LIMIT 400""").fetchall()
    picked = [r for r in rows if r['category'] == 'Auction' or GENERIC_TITLE.match(r['title'])]
    return picked[:limit]


def enrich(path, client=None, limit=PER_RUN):
    """Read up to `limit` advert PDFs. Never raises: enrichment must not break fetching."""
    own = client is None
    client = client or Client()
    done = 0
    try:
        with connect(path) as db:
            rows = [dict(r) for r in candidates(db, limit)]
        for row in rows:
            url = row['pdf_url'] or row['url']
            details = {'source_pdf': url}
            try:
                text = pdf_text(client.get(url).content)
                if len(clean(text)) < 80:
                    details['scanned'] = True    # an image of the advert: open it to read
                else:
                    details.update(advert_details(text, row['title'])); details['text'] = clean(text)[:4000]
            except (requests.ConnectionError, requests.Timeout, OSError, TemporaryError):
                continue                          # network hiccup: try again on the next fetch
            except Exception as exc:              # blocked or unreadable: remember, do not retry every run
                details['error'] = str(exc)[:200]
            with connect(path) as db:
                update = {'details': json.dumps(details)}
                text = details.get('text', '')
                if text:
                    sale = is_asset_disposal(row['title'] + ' ' + text[:2500])
                    if sale and row['category'] != 'Auction': update['category'] = 'Auction'
                    if not sale and row['category'] == 'Auction' and not is_asset_disposal(row['title']):
                        update['category'] = category(row['title'] + ' ' + text[:1500]) or 'Tender'
                    # The facts stay in `details` (shown separately); the excerpt is never rewritten,
                    # so words like "scrap" in a summary can never feed back into classification.
                    # A clearly labelled date from the advert, kept as "extracted" (needs review).
                    if details.get('deadline') and not row['deadline']:
                        update.update(deadline=details['deadline'], deadline_origin='extracted',
                                      deadline_evidence=('From the advert PDF: ' + details['deadline_evidence'])[:700])
                db.execute('UPDATE notices SET ' + ','.join(f'{k}=?' for k in update) + ' WHERE id=?', [*update.values(), row['id']])
            done += 1
    except Exception:
        log.exception('Reading advert PDFs failed')
    finally:
        if own: client.session.close()
    return done
