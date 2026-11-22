# Goals and roadmap

## Purpose

Uganda Business Watch helps one person or a small business **find Ugandan tenders,
auctions, grants and business opportunities in time to act on them**, without
checking a dozen websites and newspapers by hand.

## Goals

Each goal says how to tell whether it is being met.

| # | Goal | How we know it is met |
|---|------|------------------------|
| 1 | **Coverage:** the main official portals and national newspapers in one place. | Sources & coverage shows each bundled source as OK; known gaps are listed below with a reason. |
| 2 | **Nothing missed in time:** relevant opportunities surface before their deadline. | New keyword matches (or new open opportunities) raise a desktop alert after the fetch that finds them. |
| 3 | **Little noise:** the default view shows what can still be acted on. | The feed opens on *Current: open & recent*; closed notices and award/minutes records are one click away, never silently dropped. |
| 4 | **Trustworthy dates:** never imply a notice is open when that is not confirmed. | Only official or user-reviewed deadlines count as *Upcoming*; everything else is *Needs review* with the evidence shown. |
| 5 | **Fails loudly, not silently:** broken sources are noticed quickly. | A source that errors, returns nothing after previously working, or drops sharply is marked *Needs attention* and badged in the sidebar. |
| 6 | **Your data is safe and private:** records, notes and saved items stay on this computer and survive mistakes. | SQLite in `data/` (not in Git); daily automatic backups (last 14 kept) plus manual `backup.py`. |
| 7 | **Easy to keep running:** minimal setup, works unattended. | One command to start; scheduled fetching; tests run on GitHub for every push. |

## Principles and non-goals

- **Respect publishers.** Obey robots.txt, use public pages and data feeds only,
  never bypass logins, paywalls or blocks (Daily Monitor and URA are left manual).
- **Personal and local.** Not a public website or a resale service; no accounts,
  no cloud database. Bing News discovery is for personal use only.
- **Not a bidding tool.** The app links to the original notice; it does not submit
  bids, pay fees or judge eligibility.
- **No guessing.** Ambiguous dates are not guessed and closing times are not invented.
- **No stored passwords.** That is why there are desktop alerts but no email/SMS.

## Done

- Official portals: eGP (procurement), PPDA bid invitations with reference numbers
  and bid details for open notices, Bank of Uganda procurement documents, KCCA, NWSC.
- Added after source research (22 Nov 2026): World Bank-financed procurement in
  Uganda (open data API), Ministry of Finance, NSSF, UBOS, UCC, Uganda Development
  Bank, ERA and UEGCL. The generic reader now understands common WordPress listing
  plugins (Download Manager cards, clickable table rows).
- Newspapers: New Vision tenders, notices and business; The Independent; news
  discovery for Daily Monitor and Ugandan business topics.
- Current-first feed with Results & awards filter; watchlist; notes; saved items;
  reviewed deadlines; CSV export.
- Desktop alerts with a test button.
- Source health warnings, automatic daily backups, GitHub test workflow.

## Next

1. **Start automatically at sign-in** (Windows Task Scheduler) so fetching and
   alerts do not depend on remembering to start the app.
2. **Deadlines from advert PDFs** for open New Vision notices, marked for review.
3. **Retry the unreachable official sites** from the research table below, and
   check donor sources: AfDB (its page lists policies more than notices) and UNGM
   (UN agencies; its notice search needs a form-based adapter).
4. **Weekly digest** in the dashboard: what is new, what closes next week.

## Source research (22 Nov 2026)

Checked with the app's own client (robots.txt respected). Added sources are above.

| Candidate | Result | Notes |
|-----------|--------|-------|
| World Bank procurement API | Added | ~200 latest Uganda notices; awards go to Results & awards. |
| Ministry of Finance, NSSF, UBOS, UCC, UDB | Added | Plain listing pages; 1–8 notices each. |
| ERA, UEGCL | Added | Needed the new WordPress card support. |
| UETCL | Not added | Listing is loaded by JavaScript; no public feed found. |
| UNRA, Makerere tenders, OPM, NITA-U | Not added | Timed out from this connection; retry later. |
| UIA | Not added | Site's HTTPS certificate setup is broken (TLS error). |
| UNBS | Not added | robots.txt disallows automated access. |
| Ministry of Health | Not added | Domain did not resolve. |

## Later / ideas

- Email digest via an app-specific password kept in Windows Credential Manager
  (only if desktop alerts prove insufficient).
- Better duplicate detection if the same tender starts appearing on several
  sources (checked on 22 Nov 2026: no overlap between eGP and PPDA).
- Per-keyword alert settings (e.g. alert only for "ICT" in Kampala).

## Known gaps

| Source | Why | What to do |
|--------|-----|------------|
| Daily Monitor tenders | Refuses automated access (HTTP 403). | Open it manually; Monitor discovery still finds its stories. |
| URA tenders | Closes every automated connection. | Open it manually. |
| New Vision tenders section | Not updated since July 2026. | Current adverts appear under New Vision notices. |
| Scanned PDF adverts | No OCR. | Open the PDF; enter a reviewed deadline. |
