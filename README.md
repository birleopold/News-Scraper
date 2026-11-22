# Uganda Business Watch

A personal Python news desk for Ugandan tenders, public bids, auctions, grants,
public notices and business stories. Flask serves the responsive dashboard;
SQLite keeps records on this computer. No account, paid API key or AI service is
needed.

## Start on Windows

Open PowerShell in this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python run.py
```

Open **http://127.0.0.1:5050**. On later runs, only the last command is needed.
Alternatively run `start.ps1` or double-click `Start Business Watch.cmd`.
Python 3.11 or later is recommended; development was verified on Python 3.14.
Do not run multiple web server processes against this workspace.

## Use your desk

1. Click **Fetch latest**. Fetching happens in the background; progress and source
   failures appear in the dashboard.
2. Filter by category, publisher/source, status or publication dates. Search titles,
   excerpts, organisations and procurement references. Unknown publication dates
   appear after dated records in the default sort and are excluded from date-range
   searches.
3. **Upcoming / due today** includes only official eGP deadlines or dates you have
   manually reviewed. A future date does not prove that a procurement remains
   active: check amendments, cancellations, conditions and closing time at source.
4. Open a notice, follow its original link, save it, mark it read, and add notes.
   Save notes independently or enter a reviewed deadline. **Use source deadline**
   removes your override. Refreshes preserve your notes and saved/read flags.
5. Add phrases in **Watchlist & settings** to highlight relevant records. This
   version provides dashboard matches, not email/SMS/push notifications.
6. Export the current filtered view to CSV, including dates, evidence and links.
7. Add public RSS/Atom feeds, HTML listings or text PDFs in **Sources & coverage**.
   A successful HTTP response alone is not considered successful HTML ingestion.

## Sources and coverage

The initial registry includes 17 sources:

- Uganda eGP public procurement and disposal tables, with page-by-page reading of
  up to 1,000 current records per table and explicit submission dates.
- Daily Monitor tender listing and Bing News discovery for Monitor stories.
- New Vision tender listing, directly readable business headlines, and discovery.
- The Independent RSS, KCCA procurement, NWSC notices, PPDA, URA and Bank of Uganda.
- Additional Bing News discovery for Ugandan auctions, bids, grants and business.

Source links were checked on 22 November 2026. Useful primary starting points:
[eGP](https://egpuganda.go.ug/bid-notices),
[Daily Monitor tenders](https://www.monitor.co.ug/uganda/jobs/tenders),
[New Vision business](https://www.newvision.co.ug/category/business?id=3),
[KCCA](https://www.kcca.go.ug/tenders),
[NWSC](https://www.nwsc.co.ug/notices-2/).

Coverage is **not exhaustive**. Sources can change or be unavailable. The first
successful full run collected 111 unique records, including 49 eGP procurements.
Direct Daily Monitor requests returned HTTP 403; the New Vision tender, PPDA and
Bank of Uganda pages did not expose readable notice links; URA disconnected.
Those entries remain visible with an explanation and a manual source link.
New Vision business and Monitor discovery worked separately. eGP's disposal table
and New Vision discovery returned no records; that is distinguished from an error.

RSS/discovery returns only the publisher/search provider's available result window.
HTML sources inspect one listing page, up to 100 relevant links; they do not crawl
entire archives or every linked document. Text PDFs can be registered as sources
(up to 30 pages and 6 MB); scanned images require manual review. OCR, authenticated
e-papers, full-text article archiving and private/premium feeds are not implemented.
The app respects robots.txt and does not bypass login pages, paywalls or blocks.
Bing RSS is an optional personal news-reader discovery source: its published usage
terms restrict it to personal non-commercial aggregation. Pause discovery sources
and obtain appropriate licensed feeds before commercial redistribution.

## Date and record semantics

- **Published** is the timestamp supplied by a feed or the official eGP record's
  `created_at`. For eGP this may reflect record creation, not newspaper publication.
- **First discovered / last seen** are the times this app observed the record.
- **Deadline** is an official structured date, an unconfirmed explicitly labelled
  date extracted from a text PDF, or a user-reviewed override.
- All application times use `Africa/Kampala` (EAT). Date-only deadlines are marked
  **Due today** throughout that calendar day; exact closing hours are not inferred.
- Ambiguous numeric dates, dates without years, and multiple competing PDF dates
  are not guessed. Extracted PDF dates require review before counting as upcoming.
- Records deduplicate by canonical URL, removing common tracking parameters. The
  same story on different URLs may still appear twice. Source sightings are stored
  separately; higher-quality metadata takes precedence over discovery snippets.
- Records are retained when a source fails or removes a notice. An old notice's
  presence is not proof it is still open. No automatic bidding or payments occur.

## Automatic fetching

By default the application checks enabled sources every three hours while the
Python process is running. The browser can be closed. Change the interval (minimum
30 minutes) or turn auto-fetch off in Settings. On first launch with no prior run,
the scheduler starts a fetch within approximately 30 seconds.

For fetching without the dashboard:

```powershell
.\.venv\Scripts\python run.py --fetch
```

To run after signing into Windows, create a Task Scheduler task using:

- Program: the absolute path to `.venv\Scripts\pythonw.exe` in this folder.
- Arguments: `"C:\Users\LEOSOFT\Desktop\NEWS BY KEYWORD\run.py"`.
- Start in: `C:\Users\LEOSOFT\Desktop\NEWS BY KEYWORD`.
- Trigger: at logon; configure **Do not start a new instance** if already running.

No Windows scheduled task has been installed automatically. Keep the computer
awake and connected for scheduled fetching. A crashed fetch remains locked for up
to two hours; the next attempt marks it interrupted and starts a fresh run. Fetch
runs and per-source errors are visible in Sources. Retry transient failures with
Fetch latest; the app never deletes earlier records because a fetch failed.

## Data, backup and local security

Database: `data/uganda_watch.sqlite3`. The `data/` folder is ignored by Git. Use:

```powershell
.\.venv\Scripts\python backup.py
```

This uses SQLite's online backup API and writes a timestamped backup under
`data/backups/`. To restore, stop the application, retain a backup of the current
database, and replace it with the selected backup (including clearing stale
SQLite WAL/SHM sidecars while the server is stopped).

The web server binds only to `127.0.0.1`; mutations require a session CSRF token.
Source URLs reject private network addresses; content is escaped and downloads
are size/time bounded. This is a personal local app, not a hardened public service.
Do not expose it to the internet without authentication, deployment hardening,
network-level outbound restrictions and a production WSGI server. DNS prechecks
are not a complete DNS-rebinding defense in a hostile network environment.

## Development and checks

```powershell
.\.venv\Scripts\python -m pytest -q
```

Tests use temporary databases and fixture responses, never the personal database.
The checks cover deadline classification, reviewed-date overrides, duplicate
precedence, annotation retention, source failures, concurrent-run locking, feed
normalisation, eGP pagination, search/watchlists, CSRF, private URLs and CSV formula
escaping. Network availability remains an independent live integration check.

Main code: `ugwatch/collectors.py` (source adapters), `db.py` (SQLite), `service.py`
(fetch orchestration and scheduler), `app.py` (HTTP API), `templates/` and `static/`
(dashboard). Extend `SOURCES` in `ugwatch/sources.py` to add bundled sources.
#   N e w s - S c r a p e r  
 