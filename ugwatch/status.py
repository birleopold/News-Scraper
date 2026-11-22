"""Deadline status rules shared by the dashboard and alerts."""
import re
from datetime import date, timedelta

RECENT_DAYS = 45
OUTCOME = re.compile(r'best[ -]evaluated[ -]bidder|\bBEB\b|\bminutes\b|bid[ -]opening[ -]record|record of (?:the )?bid[ -]opening|'
                     r'notice of (?:intention to )?award|contract award|\bawarded\b', re.I)


def annotate(r, terms, today):
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
    r['recent'] = ((r['published_at'] or r['first_seen'] or '')[:10]) >= (today - timedelta(days=RECENT_DAYS)).isoformat()
    r['current'] = r['status'] in ('Upcoming', 'Due today') or (r['status'] in ('Needs review', 'News') and r['recent'])
    hay = (r['title'] + ' ' + r['excerpt'] + ' ' + r['organization']).lower()
    r['matches'] = [t for t in terms if t.lower() in hay]
    return r
