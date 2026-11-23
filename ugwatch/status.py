"""Deadline status rules shared by the dashboard and alerts."""
import re
from datetime import date, timedelta

RECENT_DAYS = 45
STILL_LISTED_DAYS = 7
OUTCOME = re.compile(r'best[ -]evaluated[ -]bidder|\bBEB\b|\bminutes\b|bid[ -]opening[ -]record|record of (?:the )?bid[ -]opening|'
                     r'notice of (?:intention to )?award|contract award|\bawarded\b', re.I)


def annotate(r, terms, today, job_terms=None):
    """Add effective_deadline, days_left, status, recent, current and matches to a notice dict."""
    r['effective_deadline'] = r['user_deadline'] if r['deadline_reviewed'] else r['deadline']
    d = date.fromisoformat(r['effective_deadline']) if r['effective_deadline'] else None
    r['days_left'] = (d - today).days if d else None
    known = r['deadline_reviewed'] or r['deadline_origin'] == 'official'
    r['status'] = ('Expired' if d < today else 'Due today' if d == today else 'Upcoming') if d and known else 'Needs review'
    if r['category'] == 'Business' and not d: r['status'] = 'News'
    # Award notices, bid-opening records and minutes report on a process; they are not opportunities.
    if r['status'] not in ('Upcoming', 'Due today') and not r['deadline_reviewed'] and OUTCOME.search(r['title'] + ' ' + r['excerpt']):
        r['status'] = 'Result'
    # Undated backlog from a source's first fetch is never "recent": it was already there.
    seen = r['published_at'] or ('' if r.get('baseline') else r['first_seen']) or ''
    r['recent'] = seen[:10] >= (today - timedelta(days=RECENT_DAYS)).isoformat()
    r['current'] = r['status'] in ('Upcoming', 'Due today') or (r['status'] in ('Needs review', 'News') and r['recent'])
    hay = (r['title'] + ' ' + r['excerpt'] + ' ' + r['organization']).lower()
    r['matches'] = [t for t in terms if t.lower() in hay]
    r['job_matches'] = [t for t in (job_terms or []) if t.lower() in hay] if r['category'] == 'Job' else []
    if r['category'] == 'Job':
        job_status(r, d, today)
    return r


def job_status(r, d, today):
    """Jobs use any closing date the advert states (job boards rarely give official dates)."""
    if d:
        r['status'] = 'Closed' if d < today else 'Closes today' if d == today else 'Open'
        r['current'] = d >= today
    elif r['published_at']:
        r['status'] = 'Open' if r['recent'] else 'Older post'
        r['current'] = r['recent']
    else:
        # Job boards list only live vacancies: an undated post is open while it is still listed.
        listed = (r['last_seen'] or '')[:10] >= (today - timedelta(days=STILL_LISTED_DAYS)).isoformat()
        r['status'] = 'Open' if listed else 'No longer listed'
        r['current'] = listed
