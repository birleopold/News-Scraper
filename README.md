# Uganda Business Watch

A personal Python news desk for Ugandan tenders, public bids, auctions, grants,
public notices and business stories. Flask serves the responsive dashboard;
SQLite keeps records on this computer. No account, paid API key or AI service is
needed.

**Goals:** find Ugandan opportunities in time to act on them, show what can still
be acted on first, never claim a notice is open without an official or reviewed
date, warn loudly when a source breaks, and keep your data private and backed up.
See [ROADMAP.md](ROADMAP.md) for how each goal is measured, what is done, what is
next and the known gaps.

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
   The feed opens on **Current: open & recent**: notices with an upcoming official
   or reviewed deadline, plus undated notices and news first published in the last
   45 days. Expired notices, older undated items and **Results & awards** (best
   evaluated bidder notices, bid-opening records, pre-bid minutes) are hidden; the
   feed says how many and offers **Show all**. Saved opportunities always show all.
3. **Upcoming / due today** includes only official eGP/PPDA deadlines or dates you have
   manually reviewed. A future date does not prove that a procurement remains
   active: check amendments, cancellations, conditions and closing time at source.
4. Open a notice, follow its original link, save it, mark it read, and add notes.
   Save notes independently or enter a reviewed deadline. **Use source deadline**
   removes your override. Refreshes preserve your notes and saved/read flags.
5. Add phrases in **Watchlist & settings** to highlight relevant records.
   **Desktop alerts** (same page) show one Windows notification after each fetch
   that finds something new: either new keyword matches (default; quiet while the
   watchlist is empty) or any new open opportunity. Clicking it opens the dashboard.
   Use **Send test alert** to check Windows shows them (Focus/Do not disturb can
   hide them). Records already in the database are never re-alerted. Alerts need the
   app or a scheduled `run.py --fetch` to be running; email/SMS are not available.
6. Export the current filtered view to CSV, including dates, evidence and links.
7. Add public RSS/Atom feeds, HTML listings or text PDFs in **Sources & coverage**.
   A successful HTTP response alone is not considered successful HTML ingestion.

## Sources and coverage

The registry includes 26 sources:

- Uganda eGP public procurement and disposal tables, with page-by-page reading of
  up to 1,000 current records per table and explicit submission dates. Slow
  responses are retried once before the source is marked as needing attention.
- PPDA Government Procurement Portal: all bid invitations for the current financial
  year (July–June) with official submission deadlines, read from the portal's public
  data feed. Still-open notices (up to 80 per run) also get the procurement reference,
  method, bid security, bid document price and bid-opening time and place.
- Bank of Uganda procurement: bidding documents, addenda, pre-bid minutes, bid
  opening records, best-evaluated-bidder notices and disposals from last year onward
  (links go to the PDFs).
- New Vision tenders and notices from the newspaper's opportunities section (latest
  50 of each); generic headings such as "Bid notice" are labelled with the advertiser.
- Daily Monitor tender listing and Bing News discovery for Monitor stories.
- New Vision business headlines and discovery.
- The Independent RSS, KCCA procurement, NWSC notices and URA.
- World Bank-financed procurement in Uganda (public procurement API; contract
  awards are listed under Results & awards).
- Ministry of Finance, NSSF, UBOS, UCC, Uganda Development Bank, ERA and UEGCL
  procurement pages. See ROADMAP.md for sources checked but not added, and why.
- Additional Bing News discovery for Ugandan auctions, bids, grants and business.

Source links were checked on 22 November 2026. Useful primary starting points:
[eGP](https://egpuganda.go.ug/bid-notices),
[Daily Monitor tenders](https://www.monitor.co.ug/uganda/jobs/tenders),
[New Vision business](https://www.newvision.co.ug/category/business?id=3),
[KCCA](https://www.kcca.go.ug/tenders),
[NWSC](https://www.nwsc.co.ug/notices-2/).

Coverage is **not exhaustive**. Sources can change or be unavailable. A full run
on 22 November 2026 held 781 records, including 387 PPDA bid invitations, 184 Bank
of Uganda documents and 100 New Vision opportunities. Daily Monitor refuses
automated requests (HTTP 403) and URA closes the connection; the app reports this
in plain language and does not work around blocks, so open those two manually.
The New Vision tenders section had not been updated since July 2026, while its
notices section was current. eGP's disposal table and New Vision discovery returned
no records; that is distinguished from an error.

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
- Arguments: the absolute path to `run.py` in quotes, e.g. `"C:\path\to\NEWS BY KEYWORD\run.py"`.
- Start in: this folder, e.g. `C:\path\to\NEWS BY KEYWORD`.
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
`data/backups/`. The app also makes an **automatic backup** after the first fetch
each day (`uganda_watch_auto_*.sqlite3`) and keeps the latest 14; manual backups
are never deleted. To restore, stop the application, retain a backup of the current
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
(fetch orchestration, source health and scheduler), `status.py` (open/closed/result
rules), `alerts.py` (desktop notifications), `backup.py` (backups), `app.py` (HTTP
API), `templates/` and `static/` (dashboard). Extend `SOURCES` in
`ugwatch/sources.py` to add bundled sources. GitHub Actions runs the tests on
Windows and Linux for every push (`.github/workflows/tests.yml`).

A source is marked **Needs attention** when it errors, returns nothing after
previously returning records, or returns under a fifth of its last good count
(when that was 10 or more). The Sources menu shows a badge with the number.
