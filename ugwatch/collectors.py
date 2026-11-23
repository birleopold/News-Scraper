"""Bounded public-source collectors. No login/paywall bypass or browser automation."""
import ipaddress
import re
import socket
import time
from datetime import datetime
from io import BytesIO
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode, parse_qs
from urllib.robotparser import RobotFileParser

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser
from pypdf import PdfReader

from .classify import CATEGORIES, category, is_asset_disposal  # noqa: F401  (re-exported for callers)

UA = 'UgandaBusinessWatch/1.0 (personal public-news index)'
MAX_BYTES = 6 * 1024 * 1024


def clean(value):
    return ' '.join(BeautifulSoup(str(value or ''),'html.parser').get_text(' ',strip=True).split())


def canonical(url):
    p=urlsplit(url)
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path or '/',urlencode([(k,v) for k,v in parse_qsl(p.query) if not k.startswith('utm_') and k not in ('fbclid','gclid')]),''))


def public_url(url):
    p=urlsplit(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.port not in (None,80,443):
        raise ValueError('Use a public HTTP(S) URL on port 80 or 443.')
    addresses=socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Private and local network sources are not allowed.')
    return url


class Client:
    def __init__(self):
        self.session=requests.Session()
        self.session.headers['User-Agent']=UA
        self.robots={}
        self.last={}

    # Waits (seconds) before retrying a network hiccup: a dropped connection, timeout,
    # failed address lookup or a 502/503/504 "try again later" answer.
    retry_waits=(2,6)

    def _retry(self,call,is_bad=lambda result:False):
        for wait in (*self.retry_waits,None):
            try:
                result=call()
            except (requests.ConnectionError,requests.Timeout,socket.gaierror):
                if wait is None: raise
            else:
                if wait is None or not is_bad(result): return result
                result.close()
            time.sleep(wait)

    def request(self,url,method='GET',data=None,robots=True):
        for _ in range(6):
            self._retry(lambda: public_url(url))
            p=urlsplit(url); origin=f'{p.scheme}://{p.netloc}'
            if robots:
                if origin not in self.robots:
                    rr=self.request(origin+'/robots.txt',robots=False)
                    rp=RobotFileParser()
                    # RFC 9309: robots.txt "unavailable" (4xx) means no restrictions, e.g. Amazon S3
                    # answers 403 for any missing file. 429 and 5xx mean "unreachable": stay away.
                    if 400<=rr.status_code<500 and rr.status_code!=429:
                        rp.parse([])
                    else:
                        rr.raise_for_status(); rp.parse(rr.text.splitlines())
                    self.robots[origin]=rp
                rp=self.robots[origin]
                if not rp.can_fetch(UA,url):
                    raise ValueError('Access restricted by robots.txt; open this source manually.')
                delay=max(0.3,float(rp.crawl_delay(UA) or rp.crawl_delay('*') or 0))
                if delay>30:
                    raise ValueError('Source requests a long crawl delay; manual review required.')
                time.sleep(max(0,delay-(time.monotonic()-self.last.get(origin,0))))
            send=lambda: self.session.request(method,url,data=data,timeout=(8,20),allow_redirects=False,stream=True)
            with self._retry(send,lambda r:r.status_code in (502,503,504)) as r:
                self.last[origin]=time.monotonic()
                if r.is_redirect:
                    url=urljoin(url,r.headers['Location'])
                    if r.status_code in (301,302,303): method='GET'; data=None
                    continue
                chunks=[]; size=0
                for chunk in r.iter_content(65536):
                    size+=len(chunk)
                    if size>MAX_BYTES: raise ValueError('Source exceeds the 6 MB download limit.')
                    chunks.append(chunk)
                r._content=b''.join(chunks)
                return r
        raise ValueError('Too many redirects.')

    def get(self,url):
        r=self.request(url); r.raise_for_status(); return r


def iso_date(value):
    if not value: return None
    try: return parser.parse(str(value)).isoformat()
    except (ValueError,OverflowError,TypeError): return None


DATE_RX=r'(?:\d{4}-\d{2}-\d{2}|\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*,?\s*\d{4})'


def extract_deadline(text):
    # Explicit labels only; ambiguous numeric dates and multiple deadlines stay unconfirmed.
    found=[]
    for m in re.finditer(r'(?:submission deadline|closing date|deadline|submit[^.\n]{0,35}?by|no later than|auction date)[^\n.]{0,65}?('+DATE_RX+r')',text,re.I):
        raw=re.sub(r'(\d)(st|nd|rd|th)',r'\1',m.group(1),flags=re.I)
        try: found.append((parser.parse(raw).date().isoformat(),m.group(0)))
        except ValueError: pass
    if len({d for d,_ in found})==1: return found[0]
    return None, 'Multiple dates found; review the original notice.' if found else ''


def collect_feed(client,source):
    response=client.get(source['url'])
    feed=feedparser.parse(response.content)
    if not feed.entries and feed.bozo: raise ValueError('This URL did not return a readable RSS/Atom feed.')
    items=[]
    for entry in feed.entries[:150]:
        title=clean(entry.get('title','')); excerpt=clean(entry.get('summary',''))
        kind=category(title+' '+excerpt)
        link=entry.get('link','')
        if source['kind']=='search' and urlsplit(link).hostname in ('www.bing.com','bing.com'):
            link=parse_qs(urlsplit(link).query).get('url',[link])[0]
        if not title or not kind or urlsplit(link).scheme not in ('http','https'): continue
        publisher=clean(entry.get('source',{}).get('title') or entry.get('news_source') or source['name'])
        items.append(dict(url=canonical(link),title=title,excerpt=excerpt[:700],category=kind,publisher=publisher,
                          published_at=iso_date(entry.get('published') or entry.get('updated')),
                          deadline_origin='discovery' if source['kind']=='search' else 'feed'))
    return items, f'{len(feed.entries)} feed entries checked. '+('Search-index discovery; confirm dates at the publisher.' if source['kind']=='search' else 'RSS feed; linked notices may contain more detail.')


def collect_egp(client,source,scope='current'):
    page=client.get('https://egpuganda.go.ug/bid-notices')
    soup=BeautifulSoup(page.content,'html.parser')
    token=soup.select_one('input[name="_token"]')
    if not token: raise ValueError('eGP page structure changed: missing public table token.')
    disposal=source['kind']=='egp_disposal'
    endpoint='https://egpuganda.go.ug/public-'+('disposals' if disposal else 'bids')+'/api-archived-notices/ajax'
    items=[]; total=0
    for start in range(0,1000,25):
        r=client.request(endpoint,'POST',{'scope':scope,'_token':token['value'],'draw':1,'start':start,'length':25})
        r.raise_for_status(); payload=r.json()
        if 'data' not in payload: raise ValueError('eGP returned an unexpected response.')
        total=int(payload.get('recordsFiltered',0))
        for row in payload['data']:
            links=BeautifulSoup(row.get('action_links',''),'html.parser')
            # Disposal notices link relatively ("/disposal/notice/277562/details").
            link=next((urljoin('https://egpuganda.go.ug/',a['href']) for a in links.select('a[href]')
                       if urlsplit(urljoin('https://egpuganda.go.ug/',a['href'])).hostname=='egpuganda.go.ug'),None)
            title=clean(row.get('subject_procurement') or row.get('disposal_subject') or row.get('subject_disposal') or row.get('procurement_subject') or row.get('disposal_details'))
            if not title or not link: continue
            deadline=iso_date(row.get('submission_deadline') or clean(row.get('deadline_date')))
            org=clean(row.get('procurement_name') or row.get('procuring_entity'))
            reference=clean(row.get('procurement_ref') or row.get('disposal_ref'))
            # Disposal rows put the reference before the entity: "MPIGI-LG/DPB/2022-2023/00048 Mpigi ..."
            ref=re.match(r'([A-Z0-9-]+(?:/[A-Za-z0-9-]+){2,})\s+(.*)',org)
            if ref and not reference: reference,org=ref.group(1),ref.group(2)
            if disposal:
                method=clean(row.get('Method_title') or row.get('disposal_method'))
                method=re.sub(r'^(.+?) \1$',r'\1',method)  # eGP repeats it: "Public Bidding Public Bidding"
                title=f'Disposal: {title.rstrip(". ")}'+(f' ({org})' if org else '')
            items.append(dict(url=canonical(link),title=title,excerpt=' · '.join(x for x in (org,method if disposal else '') if x),organization=org,
                              reference=reference,
                              category='Auction' if disposal else 'Tender',publisher='Uganda eGP',
                              published_at=iso_date(row.get('created_at') or clean(row.get('published_date'))),
                              deadline=deadline[:10] if deadline else None,
                              deadline_evidence='eGP submission deadline: '+(deadline[:10] if deadline else 'Not supplied'),deadline_origin='official'))
        if not payload['data'] or start+25>=total: break
    if total and not items: raise ValueError('eGP returned records but no notices could be parsed; adapter needs review.')
    return items, f'{len(items)} of {total} current table records read. Deadline times must be checked in the original notice.'


CARD_DATE=re.compile(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}, \d{4}\b')


def card_items(soup,base,source,seen,limit):
    """Notices whose link lives in a data attribute, as in common WordPress plugins:
    table rows with data-href (e.g. UEGCL) and Download Manager cards with
    data-downloadurl (e.g. ERA). The title is the nearest h2-h4 in the card."""
    items=[]
    for el in soup.select('[data-href],[data-downloadurl]'):
        if len(items)>=limit: break
        link=canonical(urljoin(base,el.get('data-downloadurl') or el.get('data-href')))
        if urlsplit(link).scheme not in ('http','https') or link in seen or link==canonical(base): continue
        card=el; heading=el.find(['h2','h3','h4'])
        for _ in range(5):
            if heading or card.parent is None: break
            card=card.parent; heading=card.find(['h2','h3','h4'])
        title=clean(heading.get_text(' ',strip=True)) if heading else ''
        # Card text often mentions funding ("grant") or the bank; only use it to confirm relevance.
        kind=category(title) or ('Tender' if category(clean(card.get_text(' ',strip=True))[:600]) else None)
        if len(title)<24 or not kind: continue
        seen.add(link)
        snippet=card.find('p')
        dated=CARD_DATE.search(card.get_text(' ',strip=True))
        items.append(dict(url=link,title=title[:300],category=kind,publisher=source['name'],deadline_origin='listing',
                          excerpt=clean(snippet.get_text(' ',strip=True))[:700] if snippet else 'Discovered on '+source['name']+'. Open the original notice for full requirements and dates.',
                          published_at=kampala_iso(dated.group(0)) if dated else upload_date(link)))
    return items


def collect_html(client,source):
    response=client.get(source['url'])
    if 'application/pdf' in response.headers.get('Content-Type','') or urlsplit(response.url).path.lower().endswith('.pdf'):
        reader=PdfReader(BytesIO(response.content))
        text='\n'.join(p.extract_text() or '' for p in reader.pages[:30])
        if not text.strip(): raise ValueError('Scanned PDF: text unavailable; OCR/manual review required.')
        deadline,evidence=extract_deadline(text)
        return [dict(url=canonical(source['url']),title=source['name'],excerpt=clean(text)[:700],category=category(text) or 'Public notice',publisher=source['name'],deadline=deadline,deadline_evidence=evidence,deadline_origin='extracted')], 'PDF text indexed (up to 30 pages). Extracted dates require review.'
    items=parse_listing(response.content,response.url,source)
    if not items: raise ValueError('No readable notice links found. Page may use JavaScript, images, or a changed layout; manual review required.')
    return items, f'{len(items)} matching links indexed from one listing page. Dates require original-notice review.'


UPLOAD_DATE=re.compile(r'/uploads/(20\d\d)/(0[1-9]|1[0-2])/')
# Display adverts on newspaper notice pages that are not opportunities.
NOT_OPPORTUNITY=re.compile(r'congratulat|celebrat|anniversar|condolence|obituar|\bhappy\b|season.?s greetings|merry christmas|in memoriam',re.I)
IMPORT_DEFAULTS={'import_tenders':'Tender','import_notices':'Public notice','import_jobs':'Job'}


def upload_date(url):
    """WordPress stores files under /uploads/YYYY/MM/; use that month as an approximate
    publication date so old PDFs on a listing are not mistaken for new notices."""
    m=UPLOAD_DATE.search(urlsplit(url).path)
    return f'{m.group(1)}-{m.group(2)}-01T00:00:00+03:00' if m else None


def parse_listing(content,base,source):
    """Notice links on one listing page (fetched live or saved by the user).

    Import-only sources (pages the site blocks for automated access, saved from the
    user's browser) take only titled adverts and default to the page's own kind."""
    default=IMPORT_DEFAULTS.get(source.get('kind'))
    soup=BeautifulSoup(content,'html.parser')
    for el in soup.select('nav,header,footer,script,style,aside,form'): el.decompose()
    items=[]; seen=set()
    for a in soup.select('a[href]'):
        heading=a.find(['h2','h3','h4'])
        if default and not heading: continue
        title=clean(heading.get_text(' ',strip=True) if heading else a.get_text(' ',strip=True)); link=canonical(urljoin(base,a['href'].strip()))
        if urlsplit(link).hostname in ('www.newvision.co.ug','newvision.co.ug') and 'NV_' not in urlsplit(link).path: continue
        if re.match(r'^(view (all|more)|read more|download document)$',title,re.I) and not urlsplit(link).path.lower().endswith('.pdf'): continue
        if urlsplit(link).path.lower().endswith('.pdf') and len(title)<24:
            # PDF buttons often say only 'download'; use nearby notice text, never an entire page.
            parent=a.parent
            for _ in range(4):
                if parent is None: break
                context=clean(parent.get_text(' ',strip=True))
                if 40<len(context)<1200 and category(context):
                    title=context[:350]; break
                parent=parent.parent
        kind=category(title)
        if not kind and '/category/business/' in urlsplit(link).path: kind='Business'
        if not kind and default and not NOT_OPPORTUNITY.search(title): kind=default
        if not kind or len(title)<24 or link in seen or link==canonical(base) or urlsplit(link).scheme not in ('http','https'): continue
        seen.add(link)
        # The advert text is inside the link on most sites, or just after it (Daily Monitor).
        snippet=a.find('p') or a.find_next_sibling(['p','div'])
        text=clean(snippet.get_text(' ',strip=True)) if snippet else ''
        excerpt=text[:700] if len(text)>20 else 'Discovered on '+source['name']+'. Open the original notice for full requirements and dates.'
        items.append(dict(url=link,title=title[:300],excerpt=excerpt,category=kind,publisher=source['name'],deadline_origin='listing',
                          published_at=upload_date(link)))
        if len(items)>=100: break
    items+=card_items(soup,base,source,seen,100-len(items))
    return items


def kampala_iso(value):
    """Parse an API timestamp; naive values are treated as Kampala time (EAT)."""
    if not value: return None
    try: stamp=parser.parse(str(value))
    except (ValueError,OverflowError,TypeError): return None
    from .db import EAT
    return (stamp.replace(tzinfo=EAT) if stamp.tzinfo is None else stamp.astimezone(EAT)).isoformat(timespec='seconds')


def financial_year(today=None):
    """Uganda's government financial year runs 1 July to 30 June, e.g. '2026-2027'."""
    from .db import EAT
    today=today or datetime.now(EAT).date()
    start=today.year if today.month>=7 else today.year-1
    return f'{start}-{start+1}'


def retrying(call,retries=1,pause=2):
    """Run call(), retrying transient network failures (slow government servers)."""
    for attempt in range(retries+1):
        try:
            return call()
        except (requests.Timeout,requests.ConnectionError):
            if attempt==retries: raise
            time.sleep(pause)


def get_json(client,url,retries=0):
    return retrying(lambda: client.get(url).json(),retries)


def money(value):
    try:
        value=float(value or 0)
    except (TypeError,ValueError):
        return ''
    return f'UGX {value:,.0f}' if value>0 else ''


PPDA_DETAIL_LIMIT=80


def ppda_detail(client,notice_id):
    """Fetch one notice's public details; returns {} when unavailable so listing data still counts."""
    try:
        rows=get_json(client,f'https://cdn.ppda.go.ug/api/tender/notices/{int(notice_id)}',retries=0).get('data')
    except (requests.RequestException,ValueError,AttributeError):
        return {}
    return rows[0] if isinstance(rows,list) and rows and isinstance(rows[0],dict) else {}


def collect_ppda(client,source):
    fy=financial_year()
    payload=get_json(client,'https://cdn.ppda.go.ug/api/tender/notices?'+urlencode({'fy':fy}))
    rows=payload.get('data') if isinstance(payload,dict) else None
    if not isinstance(rows,list): raise ValueError('PPDA portal returned an unexpected response; adapter needs review.')
    from .db import EAT
    today=datetime.now(EAT).date().isoformat()
    items=[]; enriched=0
    for row in rows:
        title=clean(row.get('title')); notice_id=row.get('id')
        if not title or not notice_id: continue
        entity=clean(row.get('entity'))
        deadline=(iso_date(row.get('deadline')) or '')[:10] or None
        # Only still-open notices get the extra detail request, keeping each run small.
        detail={}
        if deadline and deadline>=today and enriched<PPDA_DETAIL_LIMIT:
            detail=ppda_detail(client,notice_id); enriched+=1
        details=[entity,clean(detail.get('procurement_method')),clean(row.get('procurement_type')),clean(row.get('sector'))]
        if money(row.get('estimatedValue')): details.append('Estimated '+money(row.get('estimatedValue')))
        if money(detail.get('bid_security_amount')): details.append('Bid security '+money(detail.get('bid_security_amount')))
        if money(detail.get('bid_document_price')): details.append('Bid document '+money(detail.get('bid_document_price')))
        evidence='PPDA portal bid submission deadline: '+(deadline or 'Not supplied')
        opening_time=clean(detail.get('bid_openning_time'))[:5]
        if opening_time and opening_time!='00:00':
            evidence+=f'; bids opened at {opening_time}'+(f" ({clean(detail.get('bid_openning_address'))})" if clean(detail.get('bid_openning_address')) else '')
        if clean(detail.get('bid_reciept_address')):
            evidence+='; submit to '+clean(detail.get('bid_reciept_address'))
        evidence+='. Confirm the exact closing time in the notice.'
        items.append(dict(url=canonical(f'https://gpp.ppda.go.ug/public/bid-invitations/tender-notice/{int(notice_id)}'),
                          title=title,excerpt=' · '.join(d for d in details if d)[:700],organization=entity,
                          reference=clean(detail.get('procurement_reference_no')),
                          category=category(title) if category(title) in ('Tender','Auction','Grant') else 'Tender',
                          publisher='PPDA procurement portal',deadline=deadline,
                          deadline_evidence=evidence[:700],deadline_origin='official'))
    return items, f'{len(items)} bid invitations read for financial year {fy}; {enriched} open notices enriched with reference numbers and bid details.'


BOU_CATEGORIES={'Bidding Documents':'Tender','Disposal':'Auction','Best Evaluated Bidder Notice':'Bid',
                'Prebid Minutes':'Bid','Clarifications/Addenda':'Bid','Bid Opening Records':'Bid'}


def collect_bou(client,source):
    from .db import EAT
    payload=get_json(client,'https://bou.or.ug/api/procurement?populate=items.items.items.items.file')
    groups=(payload.get('data') or {}).get('items') if isinstance(payload,dict) else None
    if not isinstance(groups,list): raise ValueError('Bank of Uganda returned an unexpected response; adapter needs review.')
    oldest=datetime.now(EAT).year-1
    items=[]; seen=set()
    for group in groups:
        group_name=clean(group.get('category')) or 'Procurement'
        for year in group.get('items') or []:
            try:
                if int(year.get('year'))<oldest: continue
            except (TypeError,ValueError): continue
            for month in year.get('items') or []:
                for doc in month.get('items') or []:
                    files=doc.get('file') or []
                    file=files[0] if isinstance(files,list) and files else files if isinstance(files,dict) else None
                    if not file or not file.get('url'): continue
                    link=canonical(urljoin('https://bou.or.ug/',file['url']))
                    title=clean(doc.get('title'))
                    if title.endswith('...') or ' ' not in title: title=clean(doc.get('description')) or title
                    if ' ' not in title: title=title.replace('-',' ')
                    if not title or link in seen: continue
                    seen.add(link)
                    items.append(dict(url=link,title=title,
                                      excerpt=f'Bank of Uganda · {group_name} · {clean(month.get("month"))} {year.get("year")}'.strip(),
                                      organization='Bank of Uganda',category=BOU_CATEGORIES.get(group_name,'Bid'),
                                      publisher='Bank of Uganda',published_at=kampala_iso(file.get('createdAt')),
                                      deadline_origin='listing'))
    return items, f'{len(items)} procurement documents from {oldest} onwards (bidding documents, addenda, minutes, BEB notices, disposals). Open the PDF for deadlines.'


GENERIC_TITLE=re.compile(r'^(?:abridged |re-?)?(?:procurement notice|tender notice|invitation (?:to|for) (?:tender|bids?)|bid (?:notice|announcement)|'
                         r'(?:request for )?expressions? of interest\W*(?:\{?eoi\)?)?|prequalification notice|notice|public notice|notice of application)\s*$',re.I)
NV_TAG_SKIP={'new vision','news','tender','tenders','notice','notices','opportunities'}


def collect_newvision(client,source):
    section='Tenders' if source['kind']=='newvision_tenders' else 'Notices'
    rows=get_json(client,f'https://api.newvisionapp.com/V1/Opportunities/{section}?limit=72&offset=0')
    if not isinstance(rows,list): raise ValueError('New Vision returned an unexpected response; adapter needs review.')
    items=[]
    for row in rows:
        title=clean(row.get('title')); notice_id=row.get('id')
        if not title or not notice_id: continue
        body=clean(row.get('plain_text_description') or row.get('description') or row.get('summary'))
        org=next((clean(t) for t in row.get('tags') or [] if clean(t).lower() not in NV_TAG_SKIP),'')
        if org:
            # Tags are lower-case; restore acronyms such as "(hpi)" or "cglc".
            org=re.sub(r'\(([A-Za-z]{2,6})\)',lambda m:'('+m.group(1).upper()+')',org.title())
            if ' ' not in org and len(org)<=5: org=org.upper()
        if GENERIC_TITLE.match(title) and org: title=f'{title.title()}: {org}'
        default='Tender' if section=='Tenders' else 'Public notice'
        kind=category(title+' '+body) or default
        if section=='Notices' and kind=='Business' and not category(title): kind=default
        deadline,evidence=extract_deadline(body)
        items.append(dict(url=canonical(f'https://www.newvision.co.ug/opportunities/{section.lower()}-{int(notice_id)}'),
                          title=title[:300],excerpt=body[:700] or clean(row.get('summary'))[:700],organization=org,
                          category=kind,publisher='New Vision',published_at=kampala_iso(row.get('created_on')),
                          pdf_url=row['file_upload'] if str(row.get('file_upload') or '').lower().startswith('http') else None,
                          deadline=deadline,deadline_evidence=evidence or ('Full advert PDF: '+row['file_upload'] if row.get('file_upload') else ''),
                          deadline_origin='extracted' if deadline else 'listing'))
    return items, f'{len(items)} latest New Vision {section.lower()} read. Full adverts are PDFs; extracted dates require review.'


class TemporaryError(ValueError):
    """A failure that is usually short-lived (network down, site overloaded), as opposed
    to a block or a changed page. Sources that worked before are not flagged for it at once."""


def friendly_error(exc):
    status=exc.response.status_code if isinstance(exc,requests.HTTPError) and exc.response is not None else None
    if status in (401,403):
        return ValueError(f'The site refused automated access (HTTP {status}). Open it manually; this app does not bypass blocks.')
    if status in (429,500,502,503,504):
        return TemporaryError(f'The site reported a temporary problem (HTTP {status}).')
    if isinstance(exc,socket.gaierror) or 'getaddrinfo' in str(exc) or 'NameResolution' in str(exc):
        return TemporaryError("Couldn't look up the site's address. The internet connection may have been down (for example just after the computer woke up), or the site's domain has a problem.")
    if isinstance(exc,requests.Timeout):
        return TemporaryError('The site did not respond in time.')
    if isinstance(exc,(requests.ConnectionError,ConnectionError)):
        return TemporaryError('The site closed or refused the connection. It may be down, or blocking automated requests.')
    return ValueError(str(exc)[:300])


WORLDBANK_API='https://search.worldbank.org/api/v2/procnotices'


def collect_worldbank(client,source):
    """World Bank-financed procurement in Uganda from the Bank's open procurement API."""
    payload=get_json(client,WORLDBANK_API+'?'+urlencode({'format':'json','rows':200,'srt':'noticedate','order':'desc','project_ctry_name_exact':'Uganda'}))
    rows=payload.get('procnotices') if isinstance(payload,dict) else None
    if not isinstance(rows,list): raise ValueError('World Bank returned an unexpected response; adapter needs review.')
    items=[]
    for row in rows:
        notice_id=clean(row.get('id')); title=clean(row.get('bid_description')); kind_name=clean(row.get('notice_type'))
        if not notice_id or not title or not re.fullmatch(r'[A-Z0-9]+',notice_id): continue
        org=clean(row.get('contact_organization'))
        award='award' in kind_name.lower()
        deadline=None if award else (iso_date(row.get('submission_deadline_date')) or '')[:10] or None
        time_note=clean(row.get('submission_deadline_time'))
        evidence=f'World Bank notice submission deadline: {deadline}'+(f' {time_note} local time' if time_note and time_note!='00:00' else '')+'.' if deadline else ''
        details=[kind_name,org,clean(row.get('project_name')),clean(row.get('procurement_method_name'))]
        items.append(dict(url=f'https://projects.worldbank.org/en/projects-operations/procurement-detail/{notice_id}',
                          title=title[:300],excerpt=' · '.join(d for d in details if d)[:700],organization=org,
                          reference=clean(row.get('bid_reference_no')),
                          category='Bid' if award else (category(kind_name+' '+title) if category(kind_name+' '+title) in ('Tender','Grant','Auction') else 'Tender'),
                          publisher='World Bank procurement',published_at=kampala_iso(row.get('noticedate')),
                          deadline=deadline,deadline_evidence=evidence,deadline_origin='official' if deadline else 'feed'))
    return items, f'{len(items)} latest World Bank-financed notices for Uganda (bids, expressions of interest and contract awards) from the public procurement API.'


JOB_LINKS={
    # Links to individual job posts on each job site (everything else on the page is navigation).
    'www.brightermonday.co.ug':r'^/listings/[a-z0-9-]+-[a-z0-9]{6}/?$',  # job slugs end in a 6-character code
    'www.greatugandajobs.com':r'/job-detail/',
    'www.nssfug.org':r'/featured-jobs/.+',
}
GENERIC_JOB_LINK=r'/(?:jobs?|listings|vacanc\w*|careers?)/[^/?#]{6,}'
NOT_A_JOB_TITLE=re.compile(r'^(apply( now)?|view( all)?( jobs)?|visit|read more|learn more|details|more|sign in|register|post (a )?jobs?)\b',re.I)


def job_organization(title):
    """'Accountant at HR Consults Uganda' -> 'HR Consults Uganda'."""
    m=re.search(r'\s(?:job\s)?at\s+(.{3,80})$',title,re.I)
    return clean(m.group(1)) if m else ''


def collect_jobs_feed(client,source):
    """Job-board RSS (e.g. WordPress Job Manager); reads up to three feed pages."""
    entries=[]
    for page in (1,2,3):
        url=source['url']+(('&' if '?' in source['url'] else '?')+f'paged={page}' if page>1 else '')
        try: feed=feedparser.parse(client.get(url).content)
        except (requests.HTTPError,ValueError):
            if page==1: raise
            break
        if not feed.entries: break
        entries+=feed.entries
    if not entries: raise ValueError('This URL did not return any job feed entries.')
    items=[]; seen=set()
    for entry in entries:
        title=clean(entry.get('title','')); link=entry.get('link','')
        if not title or urlsplit(link).scheme not in ('http','https') or canonical(link) in seen: continue
        seen.add(canonical(link))
        body=clean((entry.get('content') or [{}])[0].get('value') or entry.get('summary',''))
        deadline,evidence=extract_deadline(body)
        items.append(dict(url=canonical(link),title=title[:300],excerpt=clean(entry.get('summary',''))[:700],category='Job',
                          publisher=source['name'],organization=job_organization(title),published_at=iso_date(entry.get('published')),
                          deadline=deadline,deadline_evidence=evidence,deadline_origin='extracted' if deadline else 'feed'))
    return items, f'{len(items)} latest job posts read from the feed.'


def collect_job_listing(client,source):
    """Job posts on one job-board page: links to individual posts, with the card text as excerpt."""
    response=client.get(source['url'])
    soup=BeautifulSoup(response.content,'html.parser')
    for el in soup.select('nav,header,footer,script,style,form'): el.decompose()
    page_host=urlsplit(response.url).hostname
    pattern=JOB_LINKS.get(page_host,GENERIC_JOB_LINK)
    found={}
    for a in soup.select('a[href]'):
        link=canonical(urljoin(response.url,a['href'].strip()))
        parts=urlsplit(link); title=clean(a.get_text(' ',strip=True))
        if parts.scheme not in ('http','https') or len(title)<5 or NOT_A_JOB_TITLE.match(title) or re.search(r'learn more$|\(\d+\)$',title,re.I): continue  # '(25)' = a category count
        external_job=parts.hostname!=page_host and (re.match(r'(jobs|careers)\.',parts.hostname or '') or '/job' in parts.path)
        if not (re.search(pattern,parts.path) or (page_host=='uganda.un.org' and external_job)): continue
        card=a
        for _ in range(6):
            if card.parent is None: break
            card=card.parent
            if len(clean(card.get_text(' ',strip=True)))>len(title)+40: break
        text=clean(card.get_text(' ',strip=True))
        if len(text)>1500: text=''
        if link not in found or len(title)>len(found[link][0]): found[link]=(title,text)
    items=[]
    for link,(title,text) in list(found.items())[:100]:
        deadline,evidence=extract_deadline(text)
        rest=text.replace(title,'',1).strip(' -·|')
        # Job cards often start with the employer's logo letter: "S SMARTEC ELECTRONICS LTD New (posted Today) ..."
        rest=re.sub(r'^[A-Z]\s{1,3}(?=[A-Z0-9])','',rest)
        employer=re.match(r'(.{3,80}?)\s+(?:New\b|Posted\b|\(posted)',rest)
        items.append(dict(url=link,title=title[:300],excerpt=(rest or 'Open the job post for requirements and how to apply.')[:500],
                          category='Job',publisher=source['name'],organization=job_organization(title) or (clean(employer.group(1)) if employer else ''),
                          deadline=deadline,deadline_evidence=evidence,deadline_origin='extracted' if deadline else 'listing'))
    if not items: raise ValueError('No job posts found. The page may load jobs with JavaScript or have changed layout.')
    return items, f'{len(items)} job posts read from one listing page.'


ADAPTERS={'jobs_rss':collect_jobs_feed,'jobs_html':collect_job_listing,'worldbank':collect_worldbank,'ppda':collect_ppda,'bou':collect_bou,'newvision_tenders':collect_newvision,'newvision_notices':collect_newvision}


def mark_disposals(items):
    """Disposals are the top priority: whatever a source called a notice (tender, BEB, bid
    document, public notice), an asset sale is filed under Disposals & auctions."""
    for item in items:
        if item.get('category') not in ('Job','Auction') and is_asset_disposal(item.get('title','')+' '+(item.get('excerpt') or '')[:400]):
            item['category']='Auction'
    return items


def collect(source):
    client=Client()
    try:
        if source['kind'] in ('rss','search'): items,message=collect_feed(client,source)
        elif source['kind'] in ('egp','egp_disposal'): items,message=collect_egp(client,source)
        elif source['kind'] in ADAPTERS: items,message=ADAPTERS[source['kind']](client,source)
        else: items,message=collect_html(client,source)
        return mark_disposals(items),message
    except (requests.RequestException,OSError) as exc:
        # requests' errors are OSErrors too; socket.gaierror comes from the address check.
        raise friendly_error(exc) from exc
    finally: client.session.close()
