# Goals and roadmap

## Purpose

Uganda Business Watch helps one person or a small business **find Ugandan tenders,
auctions, grants and business opportunities in time to act on them**, without
checking a dozen websites and newspapers by hand.

**Top priority (set 23 Nov 2026): disposal of public assets and any other asset
sale.** Every goal below applies to disposals first.

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

## Disposals: sources and gaps (23 Nov 2026)

| Source | Status |
|--------|--------|
| eGP disposal notices (official) | Read every fetch; none current today. Relative links fixed. The public archive (59, all 2023) is not imported. |
| PPDA portal | Its disposal data is only in the entities' logged-in dashboard, not the public portal; not used. |
| New Vision tenders and notices | Read automatically; auctions and disposal adverts appear here. |
| Daily Monitor tenders and supplements | Import saved pages (Cloudflare blocks automated access); many auctions appear here. |
| Bank of Uganda, IRA, Kyambogo, NWSC and other entity pages | Disposal documents detected and filed under Disposals. |
| News discovery | Broader disposals search (disposal of, boarded off, board of survey, mortgage sale, auctioneers). |
| URA customs auctions | URA refuses automated connections; check manually. |

Done 23 Nov: advert PDFs read for assets, places, dates and bid security; filters by
asset type and place; past disposals & results per disposal; duplicate adverts merged;
procurement-law boilerplate no longer mistaken for disposals; robots.txt handling follows
RFC 9309 (a missing file, e.g. Amazon S3's 403, means no restrictions).

Done 23 Nov (second round): scanned adverts read with Windows OCR; three more disposal
searches (vehicle auctions, board of survey & scrap, property auctions); hourly eGP
disposal check; weekly Daily Monitor import reminder; bid tracker; calendar export;
disposal alerts by asset type and place; date reminders; archive of records over two
years old.

Next for disposals: court bailiff and bank auction listings, if a public source
that permits automated reading can be found; URA auctions if its site opens up.

## Next

1. **Done:** start automatically at sign-in (`install-autostart.ps1`), so fetching and
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
| UNOC, IRA, Works & Transport, Education, Local Government, Lands, Kyambogo, CAA, Electoral Commission | Added (23 Nov) | 1-74 notices each; first-fetch backlog kept out of Current. |
| Jobweb Uganda, BrighterMonday, Great Uganda Jobs, UN in Uganda, NSSF careers | Added for Jobs (23 Nov) | 54 job posts on first fetch. |
| ReliefWeb jobs API, UNDP jobs | Not added | robots.txt disallows automated access. |
| Fuzu | Not added | Job listings load by JavaScript. |
| Public Service Commission, URA careers | Not added | Timed out / dropped connections on 23 Nov; retry later. |
| Daily Monitor tenders and supplements | Import-only (23 Nov) | Cloudflare bot check blocks all automated access, including RSS and sitemaps; import pages saved in your browser. |
| Ministry of Trade, Agriculture (UCSATP page) | Not added | Mostly reports and 2019-2022 documents. |
| URSB, PAU, UWA, NARO, UIRI, Uganda Airlines, OPM | Not added | Listings load by JavaScript or have no readable links. |
| MUBS, CMA | Not added | Home page has a malformed link the client rejects; retry later. |
| NIRA, Parliament | Not added | HTTPS certificate errors. |
| Uganda Railways, Energy & Minerals, UCDA | Not added | Domains did not resolve on 23 Nov. |
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
| Daily Monitor tenders and supplements | Cloudflare bot check (HTTP 403) on every automated request. | Save the page in your browser and use **Import saved page**. |
| URA tenders | Closes every automated connection. | Open it manually. |
| New Vision tenders section | Not updated since July 2026. | Current adverts appear under New Vision notices. |
| Scanned PDF adverts | No OCR. | Open the PDF; enter a reviewed deadline. |
