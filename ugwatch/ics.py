"""Calendar files (.ics) for viewing, auction and closing dates, for Outlook or Google Calendar."""
from datetime import date, datetime, timedelta, timezone


def _escape(text):
    # RFC 5545 text: backslash, semicolon, comma and newlines must be escaped.
    return (str(text or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
            .replace('\r\n', '\\n').replace('\n', '\\n'))


def _fold(line):
    """Lines longer than 75 octets continue on the next line after a space."""
    out, raw = [], line.encode('utf-8')
    while len(raw) > 75:
        cut = 75
        while (raw[cut] & 0xC0) == 0x80: cut -= 1          # never split a UTF-8 character
        out.append(raw[:cut].decode('utf-8')); raw = b' ' + raw[cut:]
    out.append(raw.decode('utf-8'))
    return '\r\n'.join(out)


def calendar_events(records, base_url):
    """One all-day event per stated date: viewing, auction and closing."""
    events = []
    for r in records:
        facts = r.get('facts') or {}
        dates = [('Viewing', facts.get('viewing')), ('Auction', facts.get('auction_date')),
                 ('Closing date' if r['category'] != 'Auction' else 'Bids close', r.get('effective_deadline'))]
        for kind, value in dates:
            if not value: continue
            try: day = date.fromisoformat(value[:10])
            except ValueError: continue
            confirm = '' if (kind.startswith(('Closing', 'Bids')) and (r.get('deadline_origin') == 'official' or r.get('deadline_reviewed'))) \
                else ' (read from the advert; confirm it)'
            events.append({'uid': f"ugw-{r['id']}-{kind.lower().replace(' ', '-')}@uganda-business-watch",
                           'day': day, 'summary': f"{kind}: {r['title'][:120]}",
                           'description': f"{r.get('organization') or r.get('publisher') or ''}\n{kind}{confirm}.\n"
                                          f"Original notice: {r['url']}\nYour desk: {base_url}/?view=disposals",
                           'url': r['url']})
    return events


def to_ics(events):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Uganda Business Watch//EN', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
             'X-WR-CALNAME:Uganda Business Watch']
    for e in events:
        lines += ['BEGIN:VEVENT', f"UID:{e['uid']}", f'DTSTAMP:{stamp}',
                  f"DTSTART;VALUE=DATE:{e['day']:%Y%m%d}", f"DTEND;VALUE=DATE:{e['day'] + timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{_escape(e['summary'])}", f"DESCRIPTION:{_escape(e['description'])}", f"URL:{e['url']}",
                  'BEGIN:VALARM', 'ACTION:DISPLAY', f"DESCRIPTION:{_escape(e['summary'])}", 'TRIGGER:-PT15H', 'END:VALARM',
                  'END:VEVENT']
    lines.append('END:VCALENDAR')
    return '\r\n'.join(_fold(line) for line in lines) + '\r\n'
