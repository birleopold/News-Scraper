"""Windows desktop alerts for new opportunities found by a fetch run."""
import json
import logging
import os
import subprocess
import sys
from datetime import datetime

from .db import connect, now, EAT
from .status import annotate

log = logging.getLogger(__name__)

ALERT_MODES = ('matches', 'open', 'off')
# Windows PowerShell 5.1 ships with Windows and can reach the WinRT toast API.
# Notice text arrives as JSON in an environment variable and is XML-escaped here,
# so titles are never interpreted as PowerShell code or toast markup.
TOAST_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$d = $env:UGW_TOAST | ConvertFrom-Json
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
function Esc([string]$s) { [System.Security.SecurityElement]::Escape($s) }
$url = Esc $d.url
$xml = "<toast activationType=""protocol"" launch=""$url""><visual><binding template=""ToastGeneric""><text>$(Esc $d.title)</text><text>$(Esc $d.body)</text><text placement=""attribution"">Uganda Business Watch</text></binding></visual><actions><action content=""Open dashboard"" activationType=""protocol"" arguments=""$url""/></actions></toast>"
$doc = New-Object Windows.Data.Xml.Dom.XmlDocument
$doc.LoadXml($xml)
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($doc))
'''


def send_toast(title, body, url):
    """Show a Windows notification. Returns (ok, message)."""
    if sys.platform != 'win32':
        return False, 'Desktop alerts are only available on Windows.'
    powershell = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
    env = dict(os.environ, UGW_TOAST=json.dumps({'title': title[:120], 'body': body[:600], 'url': url}))
    try:
        result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', TOAST_SCRIPT],
                                env=env, capture_output=True, text=True, timeout=30,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f'Could not show the notification: {exc}'
    if result.returncode:
        return False, 'Windows refused the notification: ' + (result.stderr.strip().splitlines() or ['unknown error'])[-1][:200]
    return True, 'Notification shown.'


def settings(db):
    return dict(db.execute('SELECT key,value FROM settings').fetchall())


def dashboard_url(values, view):
    return f"http://127.0.0.1:{values.get('dashboard_port', '5050')}/?view={view}"


def run_alert_items(db, started_at, mode):
    """Notices first seen during this run that the chosen alert mode cares about."""
    if mode == 'off': return []
    terms = [r['term'] for r in db.execute('SELECT term FROM watchwords')]
    if mode == 'matches' and not terms: return []
    today = datetime.now(EAT).date()
    rows = [annotate(dict(r), terms, today) for r in db.execute('SELECT * FROM notices WHERE first_seen>=? ORDER BY deadline IS NULL,deadline,id', (started_at,))]
    if mode == 'matches': return [r for r in rows if r['matches'] and r['current']]
    return [r for r in rows if r['status'] in ('Upcoming', 'Due today') or (r['matches'] and r['current'])]


def summary(items, mode):
    noun = 'keyword match' if mode == 'matches' else 'open opportunity'
    plural = 'keyword matches' if mode == 'matches' else 'open opportunities'
    title = f'{len(items)} new {noun if len(items) == 1 else plural}'
    lines = []
    for r in items[:3]:
        due = f" (closes {datetime.fromisoformat(r['effective_deadline']).strftime('%d %b')})" if r['effective_deadline'] else ''
        lines.append('• ' + r['title'][:90] + due)
    if len(items) > 3: lines.append(f'+ {len(items) - 3} more on your dashboard')
    return title, '\n'.join(lines)


def record(db, message):
    db.execute("INSERT OR REPLACE INTO settings VALUES ('last_alert',?)", (f'{now()}|{message}',))


def notify_run(path, run_id, sender=None):
    """Send one summary alert for a finished run. Never raises: alerts must not break fetching."""
    try:
        with connect(path) as db:
            values = settings(db)
            mode = values.get('alert_mode', 'matches')
            run = db.execute('SELECT started_at FROM runs WHERE id=?', (run_id,)).fetchone()
            items = run_alert_items(db, run['started_at'], mode) if run else []
        if not items: return 0
        title, body = summary(items, mode)
        ok, message = (sender or send_toast)(title, body, dashboard_url(values, 'matches' if mode == 'matches' else 'all'))
        with connect(path) as db:
            record(db, f'{title}. {message}' if ok else message)
        if not ok: log.warning('Alert not shown: %s', message)
        return len(items) if ok else 0
    except Exception:
        log.exception('Alert failed')
        return 0


def send_test(path, sender=None):
    with connect(path) as db:
        values = settings(db)
    ok, message = (sender or send_toast)('Alerts are working', 'New opportunities will appear like this after each fetch.', dashboard_url(values, 'all'))
    with connect(path) as db:
        record(db, ('Test alert. ' + message) if ok else message)
    return ok, message
