import csv
import io
import os
import re
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, jsonify, render_template, request, session, Response

from .alerts import ALERT_MODES, notify_run, send_test
from .collectors import CATEGORIES, mark_disposals, parse_listing, public_url
from .db import connect, init_db, EAT, now, upsert_notice
from .service import start_run
from .sources import seed
from .ics import calendar_events, to_ics
from .classify import ASSET_TYPES, PLACES
from .duplicates import mark_duplicates
from .enrich import reclassify
from .status import annotate as annotate_status


STATUS_FILTERS=('','current','open','week','review','expired','results')
PIPELINE=('','interested','viewed','bid','won','lost')
ASSET_NAMES={name for name,_ in ASSET_TYPES}
MAX_IMPORT_BYTES=6*1024*1024


def saved_page_url(content):
    """The address a browser-saved page came from: Chrome/Edge add a 'saved from url'
    comment, and most pages declare a canonical or og:url link."""
    head=content[:200_000].decode('utf-8','ignore')
    m=(re.search(r'saved from url=\(\d+\)(\S+)',head) or re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)',head,re.I)
       or re.search(r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)',head,re.I))
    return m.group(1) if m else None


def create_app(database=None):
    app=Flask(__name__,template_folder='../templates',static_folder='../static')
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32),
                      DATABASE=str(database or Path(__file__).resolve().parent.parent/'data'/'uganda_watch.sqlite3'),
                      MAX_CONTENT_LENGTH=MAX_IMPORT_BYTES+64*1024,SESSION_COOKIE_SAMESITE='Strict',
                      TRUSTED_HOSTS=['127.0.0.1','localhost','[::1]'])
    init_db(app.config['DATABASE'])
    with connect(app.config['DATABASE']) as db:
        seed(db)
        reclassify(db)   # apply the current disposal rules to stored notices
    # Version tag for /static URLs so browsers fetch the script and styles that match this page.
    static=Path(app.static_folder)
    build=format(int(max(f.stat().st_mtime for f in [static/'style.css',*static.glob('js/*.js')])),'x')

    @app.before_request
    def csrf():
        if request.method in ('POST','PUT','PATCH','DELETE'):
            token=session.get('csrf')
            if not token or not secrets.compare_digest(token,request.headers.get('X-CSRF-Token','')): abort(403)

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def errors(e): return jsonify(error=e.description),e.code

    @app.get('/')
    def home():
        session.setdefault('csrf',secrets.token_hex(32))
        return render_template('index.html',csrf=session['csrf'],build=build)

    def rows():
        with connect(app.config['DATABASE']) as db:
            records=[dict(r) for r in db.execute('SELECT n.*,s.name AS source_name,s.kind AS source_kind FROM notices n JOIN sources s ON n.source_id=s.id ORDER BY n.published_at IS NULL,n.published_at DESC,n.first_seen DESC,n.id DESC')]
            terms=[r['term'] for r in db.execute('SELECT term FROM watchwords')]
            job_terms=[r['term'] for r in db.execute('SELECT term FROM job_words')]
        today=datetime.now(EAT).date()
        return mark_duplicates([annotate_status(r,terms,today,job_terms) for r in records])

    def filtered(records,status=None):
        q=request.args.get('q','').lower().strip()
        for key in ('from','to'):
            value=request.args.get(key)
            if value:
                try: date.fromisoformat(value)
                except ValueError: abort(400,'Invalid date filter.')
        status=request.args.get('status','') if status is None else status
        if status not in STATUS_FILTERS: abort(400,'Invalid status filter.')
        view=request.args.get('view','all')
        # Search always reaches the archive; lists show it only when asked.
        include_archive=request.args.get('archived')=='1' or bool(q)
        result=[]
        for r in records:
            if (view=='jobs')!=(r['category']=='Job'): continue
            if view=='jobs' and request.args.get('mine')=='1' and not r['job_matches']: continue
            if view=='disposals' and r['category']!='Auction': continue
            if r.get('duplicate_of') and request.args.get('dupes')!='1': continue
            if r['archived'] and not include_archive: continue
            stage=request.args.get('pipeline')
            if stage=='any' and not r['pipeline']: continue
            if stage and stage!='any' and r['pipeline']!=stage: continue
            if request.args.get('asset') and request.args['asset'] not in r['assets']: continue
            if request.args.get('place') and request.args['place'] not in r['places']: continue
            if q and q not in ' '.join(str(r[k] or '') for k in ('title','excerpt','organization','reference','publisher')).lower(): continue
            if request.args.get('category') and r['category']!=request.args['category']: continue
            if request.args.get('source') and str(r['source_id'])!=request.args['source']: continue
            if status=='current' and not r['current']: continue
            if status=='results' and r['status']!='Result': continue
            if status=='open' and r['status'] not in ('Upcoming','Due today'): continue
            if status=='review' and r['status']!='Needs review': continue
            if status=='expired' and r['status']!='Expired': continue
            if status=='week' and not (r['status'] in ('Upcoming','Due today') and r['days_left']<=7): continue
            if view=='saved' and not r['saved']: continue
            if view=='matches' and not r['matches']: continue
            if view=='unread' and r['read']: continue
            if request.args.get('discovered')=='today' and r['first_seen'][:10]!=datetime.now(EAT).date().isoformat(): continue
            pub=(r['published_at'] or '')[:10]
            if request.args.get('from') and (not pub or pub<request.args['from']): continue
            if request.args.get('to') and (not pub or pub>request.args['to']): continue
            result.append(r)
        if request.args.get('sort')=='deadline': result.sort(key=lambda r:r['effective_deadline'] or '9999')
        if request.args.get('sort')=='discovered': result.sort(key=lambda r:r['first_seen'],reverse=True)
        if request.args.get('sort')=='match':
            # Most of your job keywords first; the list is already newest-first, and sort is stable.
            result.sort(key=lambda r:len(r.get('job_matches') or []),reverse=True)
        return result

    @app.get('/api/notices')
    def notices():
        try: page=max(1,int(request.args.get('page',1)))
        except ValueError: abort(400,'Invalid page.')
        records=rows(); result=filtered(records)
        # Tell the dashboard how much the Current view hides, so nothing silently disappears.
        hidden=len(filtered(records,''))-len(result) if request.args.get('status')=='current' else 0
        archived=0 if request.args.get('archived')=='1' else sum(1 for r in records if r['archived'] and (
            (request.args.get('view')=='jobs')==(r['category']=='Job')) and (request.args.get('view')!='disposals' or r['category']=='Auction'))
        return jsonify(items=result[(page-1)*24:page*24],total=len(result),hidden=hidden,archived=archived,page=page,pages=max(1,(len(result)+23)//24))

    @app.get('/api/overview')
    def overview():
        everything=rows(); today=datetime.now(EAT).date().isoformat()
        records=[r for r in everything if r['category']!='Job' and not r.get('duplicate_of')]
        sales=[r for r in records if r['category']=='Auction']
        jobs=[r for r in everything if r['category']=='Job']
        upcoming=[r for r in records if r['status'] in ('Upcoming','Due today')]
        with connect(app.config['DATABASE']) as db:
            sources=[dict(r) for r in db.execute('SELECT * FROM sources ORDER BY id')]
            runs=[dict(r) for r in db.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 10')]
            words=[dict(r) for r in db.execute('SELECT * FROM watchwords ORDER BY term')]
            job_words=[dict(r) for r in db.execute('SELECT * FROM job_words ORDER BY term')]
            settings=dict(db.execute('SELECT key,value FROM settings').fetchall())
        return jsonify(stats=dict(total=len(records),current=sum(r['current'] for r in records),new_today=sum(r['first_seen'][:10]==today for r in records),
                                  upcoming=len(upcoming),closing_week=sum(r['days_left']<=7 for r in upcoming),
                                  review=sum(r['status']=='Needs review' and r['recent'] for r in records),saved=sum(r['saved'] for r in records),matches=sum(bool(r['matches']) for r in records),
                                  disposals=sum(r['current'] and r['category']=='Auction' for r in records),
                                  jobs_open=sum(r['current'] for r in jobs),job_matches=sum(bool(r['job_matches']) and r['current'] for r in jobs)),
                       deadlines=sorted(upcoming,key=lambda r:r['effective_deadline'])[:6],
                       disposal_facets=dict(assets=facet(sales,'assets'),places=facet(sales,'places')),
                       places=list(PLACES),asset_names=[name for name,_ in ASSET_TYPES],
                       pipeline=sum(bool(r['pipeline']) for r in records),
                       latest_disposals=[r for r in records if r['current'] and r['category']=='Auction'][:5],sources=sources,runs=runs,watchwords=words,job_words=job_words,settings=settings,today=today,categories=CATEGORIES)

    def body():
        data=request.get_json(silent=True)
        if not isinstance(data,dict): abort(400,'Expected a JSON object.')
        return data

    def facet(records,key):
        counts={}
        for r in records:
            for value in r[key]: counts[value]=counts.get(value,0)+1
        return sorted(({'name':k,'count':v} for k,v in counts.items()),key=lambda x:(-x['count'],x['name']))

    @app.get('/api/notices/<int:notice_id>/history')
    def disposal_history(notice_id):
        """Earlier disposals of the same kind of asset (same seller first), with any amounts
        their adverts state: a guide to what similar assets went for, not a valuation."""
        records=[r for r in rows() if r['category']=='Auction' and not r.get('duplicate_of')]
        target=next((r for r in records if r['id']==notice_id),None)
        if target is None: abort(404)
        org=(target['organization'] or '').lower()
        scored=[]
        for r in records:
            if r['id']==notice_id: continue
            shared=set(r['assets'])&set(target['assets'])
            same_seller=bool(org) and (r['organization'] or '').lower()==org
            if not shared and not same_seller: continue
            # Your own bids and results are the most useful guide, then the same seller.
            scored.append((4*bool(r['my_bid'] or r['outcome_amount'])+3*same_seller+len(shared)+(r['status']=='Result'),r))
        scored.sort(key=lambda x:x[1]['published_at'] or x[1]['first_seen'],reverse=True)   # newest first...
        scored.sort(key=lambda x:-x[0])                                                      # ...within each relevance level
        items=[dict(id=r['id'],title=r['title'],url=r['url'],status=r['status'],organization=r['organization'],
                    pipeline=r['pipeline'],my_bid=r['my_bid'],outcome_amount=r['outcome_amount'],
                    date=(r['published_at'] or r['first_seen'])[:10],assets=r['assets'],amounts=r['facts'].get('amounts') or [],
                    bid_security=r['facts'].get('bid_security'),auction_date=r['facts'].get('auction_date')) for _,r in scored[:8]]
        return jsonify(items=items)

    @app.post('/api/fetch')
    def fetch():
        run_id,started=start_run(app.config['DATABASE'])
        return jsonify(run_id=run_id,started=started),202

    @app.patch('/api/notices/<int:notice_id>')
    def annotate(notice_id):
        data=body(); fields={}
        for key in ('saved','read'):
            if key in data:
                if not isinstance(data[key],bool): abort(400,'Invalid flag.')
                fields[key]=int(data[key])
        if 'notes' in data: fields['notes']=str(data['notes'])[:5000]
        if 'user_deadline' in data:
            d=data['user_deadline']
            if d:
                try: date.fromisoformat(d)
                except (ValueError,TypeError): abort(400,'Use YYYY-MM-DD for the deadline.')
            fields.update(user_deadline=d or None,deadline_reviewed=1)
        if data.get('reset_deadline'): fields.update(user_deadline=None,deadline_reviewed=0)
        if 'pipeline' in data:
            if data['pipeline'] not in PIPELINE: abort(400,'Unknown tracker stage.')
            fields['pipeline']=data['pipeline']
        for key in ('my_bid','outcome_amount'):
            if key in data:
                value=data[key]
                if value in (None,''): fields[key]=None; continue
                try: value=int(str(value).replace(',',''))
                except ValueError: abort(400,'Amounts must be whole numbers of shillings.')
                if not 0<=value<=10**13: abort(400,'Amount out of range.')
                fields[key]=value
        if not fields: abort(400,'No changes provided.')
        with connect(app.config['DATABASE']) as db:
            cur=db.execute('UPDATE notices SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',list(fields.values())+[notice_id])
            if not cur.rowcount: abort(404)
        return jsonify(ok=True)

    @app.post('/api/sources')
    def add_source():
        data=body(); name=str(data.get('name','')).strip(); url=str(data.get('url','')).strip(); kind=data.get('kind')
        if not name or len(name)>150 or len(url)>2000 or kind not in ('rss','html'): abort(400,'Provide a name, public URL, and RSS or HTML type.')
        try: public_url(url)
        except (ValueError,OSError) as e: abort(400,str(e))
        with connect(app.config['DATABASE']) as db:
            if db.execute('SELECT id FROM sources WHERE url=?',(url,)).fetchone(): abort(400,'That URL is already registered.')
            db.execute('INSERT INTO sources(name,url,kind) VALUES (?,?,?)',(name,url,kind))
        return jsonify(ok=True),201

    @app.post('/api/sources/<int:source_id>/import')
    def import_saved_page(source_id):
        """Add notices from a listing page the user saved in their own browser, for
        sites that block automated access. Nothing is fetched from the site here."""
        upload=request.files.get('page')
        if upload is None: abort(400,'Choose the saved page (.html) to import.')
        content=upload.read(MAX_IMPORT_BYTES+1)
        if len(content)>MAX_IMPORT_BYTES: abort(400,'That file is larger than 6 MB. Save the page as "Webpage, HTML only".')
        if b'<a' not in content.lower()[:MAX_IMPORT_BYTES]: abort(400,'That file does not look like a saved web page. Save it with Ctrl+S as "Webpage, HTML only".')
        with connect(app.config['DATABASE']) as db:
            source=db.execute('SELECT * FROM sources WHERE id=?',(source_id,)).fetchone()
        if source is None: abort(404)
        source=dict(source)
        page_url=saved_page_url(content)
        expected=urlsplit(source['url']).hostname.removeprefix('www.')
        if page_url and urlsplit(page_url).hostname and urlsplit(page_url).hostname.removeprefix('www.')!=expected:
            abort(400,f'This file is a page from {urlsplit(page_url).hostname}, not {expected}. Save the page shown on the source card.')
        items=mark_disposals(parse_listing(content,source['url'],source))
        if not items: abort(400,'No notices were found in that file. Make sure it is the listing page itself, saved after it finished loading.')
        stamp=now()
        with connect(app.config['DATABASE']) as db:
            run_id=db.execute("INSERT INTO runs(started_at,state,checked) VALUES (?,'running',1)",(stamp,)).lastrowid
            added=sum(upsert_notice(db,source_id,item) for item in items)
            message=f'Imported {len(items)} notices ({added} new) from a page saved in your browser. Save and import the page again to pick up newer adverts.'
            db.execute("UPDATE sources SET last_checked=?,last_success=?,status='Imported',message=?,item_count=?,last_good_count=?,last_good_at=?,fail_streak=0 WHERE id=?",
                       (stamp,stamp,message,len(items),len(items),stamp,source_id))
            db.execute("UPDATE runs SET state='complete',finished_at=?,added=?,message=? WHERE id=?",(now(),added,f'Imported saved page for {source["name"]}.',run_id))
        if added: notify_run(app.config['DATABASE'],run_id)
        return jsonify(ok=True,found=len(items),added=added,message=message)

    @app.patch('/api/sources/<int:source_id>')
    def toggle_source(source_id):
        data=body()
        if not isinstance(data.get('enabled'),bool): abort(400,'Invalid enabled flag.')
        with connect(app.config['DATABASE']) as db:
            if not db.execute('UPDATE sources SET enabled=? WHERE id=?',(int(data['enabled']),source_id)).rowcount: abort(404)
        return jsonify(ok=True)

    @app.post('/api/watchwords')
    def add_word():
        term=str(body().get('term','')).strip()
        if not term or len(term)>80: abort(400,'Use a keyword or phrase up to 80 characters.')
        with connect(app.config['DATABASE']) as db: db.execute('INSERT OR IGNORE INTO watchwords(term) VALUES (?)',(term,))
        return jsonify(ok=True),201

    @app.delete('/api/watchwords/<int:word_id>')
    def delete_word(word_id):
        with connect(app.config['DATABASE']) as db: db.execute('DELETE FROM watchwords WHERE id=?',(word_id,))
        return jsonify(ok=True)

    @app.post('/api/jobwords')
    def add_job_word():
        term=str(body().get('term','')).strip()
        if not term or len(term)>80: abort(400,'Use a keyword or phrase up to 80 characters.')
        with connect(app.config['DATABASE']) as db: db.execute('INSERT OR IGNORE INTO job_words(term) VALUES (?)',(term,))
        return jsonify(ok=True),201

    @app.delete('/api/jobwords/<int:word_id>')
    def delete_job_word(word_id):
        with connect(app.config['DATABASE']) as db: db.execute('DELETE FROM job_words WHERE id=?',(word_id,))
        return jsonify(ok=True)

    @app.patch('/api/settings')
    def settings():
        data=body()
        try: interval=int(data.get('interval_minutes',180))
        except (ValueError,TypeError): abort(400,'Invalid interval.')
        if interval<30 or interval>10080 or not isinstance(data.get('auto_fetch'),bool): abort(400,'Choose an interval from 30 to 10080 minutes.')
        with connect(app.config['DATABASE']) as db:
            db.execute("UPDATE settings SET value=? WHERE key='interval_minutes'",(str(interval),))
            db.execute("UPDATE settings SET value=? WHERE key='auto_fetch'",(str(int(data['auto_fetch'])),))
        return jsonify(ok=True)

    @app.patch('/api/alerts')
    def alert_settings():
        data=body(); mode=data.get('mode')
        if mode not in ALERT_MODES: abort(400,'Choose an alert mode.')
        assets=data.get('assets',[]); places=data.get('places',[])
        if not isinstance(assets,list) or any(a not in ASSET_NAMES for a in assets): abort(400,'Unknown asset type.')
        if not isinstance(places,list) or any(p not in PLACES for p in places): abort(400,'Unknown place; choose from the list.')
        with connect(app.config['DATABASE']) as db:
            for key,value in (('alert_mode',mode),('alert_assets',','.join(assets)),('alert_places',','.join(places)),
                              ('reminders','0' if data.get('reminders') is False else '1')):
                db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,value))
        return jsonify(ok=True)

    @app.get('/api/notices/<int:notice_id>/calendar.ics')
    def notice_calendar(notice_id):
        record=next((r for r in rows() if r['id']==notice_id),None)
        if record is None: abort(404)
        return calendar_response([record],f'notice-{notice_id}.ics')

    @app.get('/api/calendar.ics')
    def my_calendar():
        """Dates of everything you track or saved: subscribe once, or download again for updates."""
        # An empty calendar is still a valid file, so subscribing before tracking anything works.
        return calendar_response([r for r in rows() if r['pipeline'] or r['saved']],'uganda-business-watch.ics',allow_empty=True)

    def calendar_response(records,filename,allow_empty=False):
        events=calendar_events(records,request.host_url.rstrip('/'))
        if not events and not allow_empty: abort(404,'No dates to add yet.')
        return Response(to_ics(events),mimetype='text/calendar',headers={'Content-Disposition':f'attachment; filename={filename}'})

    @app.post('/api/alerts/test')
    def alert_test():
        ok,message=send_test(app.config['DATABASE'])
        return jsonify(ok=ok,message=message),(200 if ok else 502)

    @app.get('/api/export')
    def export():
        output=io.StringIO(); writer=csv.writer(output)
        keys=['title','category','publisher','source_name','status','published_at','effective_deadline','deadline_origin','deadline_evidence','reference','organization','first_seen','last_seen','url','notes']
        writer.writerow(keys)
        for r in filtered(rows()):
            values=[str(r.get(k) or '') for k in keys]
            writer.writerow(["'"+v if v.lstrip().startswith(('=','+','-','@')) else v for v in values])
        return Response('\ufeff'+output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=uganda-opportunities.csv'})

    return app
