# SEC EDGAR IPO / New-Listing Detection: Sources and Latency

Research for the TODOS.md entry "Seed universe must refresh daily, scope to
active companies only, and pick up new IPOs as they start trading."

## Summary

SEC EDGAR does not expose an explicit "just IPO'd" event or flag anywhere —
there is no `is_new_listing` field or dedicated IPO feed. It must be inferred
from ordinary filing activity: a CIK's registration statement (S-1/S-11/F-1),
followed by an `EFFECT` notice of effectiveness, followed by a `424B4`/`424B3`
pricing prospectus, with a ticker subsequently appearing in the ticker
reference files. The lowest-latency place to see this happen is **not** a
bulk/reference file at all — it is SEC's own near-real-time filing surfaces:
`data.sec.gov/submissions/CIK##########.json` (SEC states sub-second
processing delay) and the "Latest Filings" feed
(`https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent`, filterable by
`type=424B4`/`type=EFFECT`/`type=S-1`), which SEC's own FAQ says is "the best
resource for getting as close to real time availability as possible," with
filings generally visible within 1–3 minutes of the EDGAR acceptance
timestamp. The reference ticker files (`company_tickers.json`,
`company_tickers_exchange.json`) and the daily-index `form.idx` feed are much
higher latency (hours to potentially a week+) and should not be the primary
signal for same-day IPO detection, contrary to what this repo's docs
currently assume. This repo's existing `sec_current_filing_feed` table is
**not actually populated by anything** — it is dead-code infrastructure, not
a working ingestion path, so a new (small) ingestion path against the
`getcurrent` feed or `stg_daily_index_filing`'s existing daily-index puller
would be needed either way.

---

## 1. Does SEC EDGAR expose an explicit "just IPO'd" signal, or is it inferred?

It is inferred. There is no dedicated "new listing" or "IPO" event/flag
anywhere in SEC's public APIs or data files that I could find in the EDGAR
API documentation page or the webmaster FAQ (both fetched and read in full,
see citations in Q2/Q3). SEC's own IPO-relevant form types are ordinary
filing types visible in the normal filing stream:

- Registration: `S-1`, `S-1/A`, `S-11`, `S-11/A`, `F-1`, `F-1/A` (and `DRS`
  for confidential draft registration, which precedes the public `S-1`).
- `EFFECT` — SEC's notice that a registration statement has been declared
  effective (a real, distinct filing/entry type, not a status field).
- `424B3`/`424B4`/`424B5`/etc. — the final prospectus that prices the
  offering.
- `8-A12B`/`8-A12G` — registration of a class of securities under an
  exchange, typically filed same-day as `EFFECT`.

I verified this end-to-end against a real, currently-in-progress IPO found
in a live daily-index file (`form.20260721.idx`, fetched
2026-07-22): **B&R Technology Merger Corp.** (CIK `2131350`, a SPAC), via
`https://data.sec.gov/submissions/CIK0002131350.json` (fetched 2026-07-22):

```
DRS       2026-06-09   (confidential draft registration)
S-1       2026-07-02   (public registration statement)
3, CERT, 8-A12B   2026-07-20   (insider ownership forms + exchange listing cert, filed same day)
EFFECT    2026-07-20   (SEC declares the registration effective)
424B4     2026-07-21   (final prospectus — the offering prices)
```

`tickers: ["BRTM"]` was already populated in that CIK's submissions.json the
day after pricing, but `exchanges: [null]` was still null at that point —
so even the richest per-CIK document doesn't reliably carry the exchange
name immediately at pricing. This confirms the sequence is a multi-step,
multi-day filing pattern that must be watched and stitched together, not a
single signal. (Source: `https://data.sec.gov/submissions/CIK0002131350.json`,
accessed 2026-07-22.)

## 2. What is the actual lowest-latency SEC source for "a new ticker/CIK just started trading"?

Ranked fastest to slowest, based on primary sources fetched directly (not
memory or secondary blogs):

1. **`data.sec.gov/submissions/CIK##########.json`** — SEC's own EDGAR API
   documentation page states: *"The JSON structures are updated throughout
   the day, in real time, as submissions are disseminated... The submissions
   API is updated with a typical processing delay of less than a second."*
   (Source: `https://www.sec.gov/search-filings/edgar-application-programming-interfaces`,
   fetched 2026-07-22, section "Update Schedule.") This is the fastest
   *structured/JSON* source, but only useful once you already know the CIK to
   poll — it is not itself a discovery feed for "which CIKs are new."

2. **EDGAR "Latest Filings" feed** —
   `https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=424B4&output=atom`
   (filterable by `type=`). SEC's webmaster FAQ states explicitly: *"Filings
   are often available on sec.gov within 1-3 minutes of the EDGAR system
   timestamp,"* and *"Our Latest Filings search and associated RSS are the
   best resources for getting as close to real time availability as
   possible."* (Source:
   `https://www.sec.gov/about/webmaster-frequently-asked-questions`, sections
   `#lag` and `#fast-access`, fetched 2026-07-22.) I fetched this feed live
   (2026-07-22 08:33 ET) filtered to `type=424B4` and it showed the B&R
   Technology Merger Corp. `424B4` from the prior afternoon
   (`<updated>2026-07-21T16:52:41-04:00</updated>`) — i.e. minutes-level
   granularity, filterable directly to the exact IPO-relevant form types.
   This is a genuine discovery feed (poll `type=424B4` or `type=EFFECT`
   without needing to know the CIK in advance) and is the practical
   candidate for this platform.

3. **Daily-index `form.YYYYMMDD.idx`** —
   `https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{n}/form.{date}.idx`.
   I fetched the real directory listing
   (`https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/index.json`,
   2026-07-22) and the file's own `last-modified` timestamps show each day's
   index is finalized and written **once, in the evening** (e.g.
   `form.20260721.idx` → `"07/21/2026 10:03:19 PM"`). I fetched that file and
   confirmed it lists `S-1`, `S-1/A`, `F-1`, `F-1/A`, `EFFECT`, and
   `424B3`/`424B4`/`424B5` entries with real CIKs and accession numbers for
   that calendar day. This is a same-day but end-of-day (batch) signal, not
   near-real-time.

4. **`company_tickers.json` / `company_tickers_exchange.json`** — slowest and
   least reliable for detection. SEC's own FAQ hedges cadence explicitly:
   *"We periodically update the file but do not guarantee accuracy or
   scope."* (Source: same FAQ page, section `#ticker-cik`.) I fetched both
   files live with HTTP HEAD-style headers (2026-07-22 12:31 UTC):
   `company_tickers.json` `Last-Modified: Tue, 21 Jul 2026 20:44:01 GMT`
   (previous day) vs. `company_tickers_exchange.json`
   `Last-Modified: Wed, 15 Jul 2026 20:47:11 GMT` (about a week stale at
   fetch time) — the two files are *not* refreshed on the same schedule, and
   neither publishes a documented cadence. Both already contained CIK
   `2131350`/ticker `BRTM` at fetch time (`company_tickers_exchange.json`
   with `exchange: null`), consistent with SEC assigning/reserving a ticker
   before the "official" listing date, but I could not establish exactly
   *when* each file first added the row (no historical snapshots available;
   the whole-file `Last-Modified` only reflects the latest write to the
   entire ~10,400-row file, not a per-row timestamp).

5. **EDGAR full text search** (`efts.sec.gov/LATEST/search-index`) — I
   queried it live for `forms=424B4&startdt=2026-07-21&enddt=2026-07-21` on
   the morning of 2026-07-22 and got 3 real hits including the B&R
   Technology Merger Corp. `424B4`. So the filing content is indexed and
   searchable by the next business day at the latest. I did not test
   same-day/intraday indexing latency, so I can't place it precisely on this
   ranking beyond "same-day-to-next-morning" — flagging this as untested
   rather than assuming near-real-time.

## 3. Practical latency between an actual IPO (first trade) and each source reflecting it

- **Filing-to-availability baseline** (applies to all of the above once a
  relevant form is actually filed): SEC's FAQ states documents are "often
  available on sec.gov within 1-3 minutes of the EDGAR system timestamp."
  (Same FAQ, section `#lag`.)
- **`data.sec.gov/submissions/...json`**: sub-second processing delay per
  SEC's own documentation, on top of the 1-3 minute filing-acceptance lag —
  effectively minutes-level once you know to poll a given CIK.
- **`getcurrent` Latest Filings feed**: minutes-level, confirmed empirically
  (an afternoon `424B4` was visible in the feed that same afternoon).
- **Daily-index `form.idx`**: same calendar day, but not published until
  roughly 10 PM ET — so up to ~10+ hours of latency depending on what time of
  day the filing happened.
- **`company_tickers*.json`**: no documented SLA; empirically ranged from
  "previous day" (`company_tickers.json`) to "about a week stale"
  (`company_tickers_exchange.json`) at the moment I sampled them. Not
  suitable as a same-day detection signal.
- Note: none of the above is literally "first trade" — SEC filings mark
  registration/effectiveness/pricing events, which happen on or immediately
  before the first trading day, not the trade itself (SEC does not publish
  trade-level or exchange-listing-start data; that lives with the exchanges/
  Nasdaq/NYSE, out of scope for EDGAR).

## 4. Can a pending IPO be detected via S-1 filing before trading starts, distinct from detecting trading start?

Yes, and this is an earlier, distinct signal from pricing/trading start.
`data.sec.gov/submissions/CIK##########.json` is queryable for a CIK as soon
as that CIK exists in EDGAR and has any public filing — in the B&R Technology
Merger Corp. example, the CIK had a `DRS` (confidential draft) on 2026-06-09
and a public `S-1` on 2026-07-02, both visible in `filings.recent`, roughly
three weeks before the `424B4` pricing on 2026-07-21 and long before any
ticker (`BRTM`) was meaningful. So: yes, "S-1 filed, registration pending" is
a legitimately earlier and separately-detectable signal (poll/watch
`type=S-1`/`type=S-11`/`type=F-1` on the `getcurrent` feed or daily-index) from
"IPO priced and trading" (watch `type=424B4`/`type=EFFECT`). A pipeline that
wants to track "in-registration" candidates ahead of them trading could seed
a provisional/pending record off the `S-1` alone, then promote it to
"active/trading" off the subsequent `EFFECT`+`424B4` pair.

## 5. Does `sec_current_filing_feed` already ingest a usable signal, or is new ingestion needed?

Based only on the code actually read (not assumption): **`sec_current_filing_feed` is dead/unpopulated infrastructure, not a working ingestion path.**

- The table is defined in
  `edgar_warehouse/silver_store.py:119-134` (DDL) with a write method
  `merge_current_filing_feed()` (`silver_store.py:1669-1715`) and a read
  method `get_current_filing_feed()` (`silver_store.py:1717-1725`).
  `merge_current_filing_feed` is registered in the table-protection policy
  (`edgar_warehouse/silver_protection.py:100-101`) and the sharded-reader
  table list (`edgar_warehouse/silver_support/sharded_reader.py:64`).
- I grepped the entire `edgar_warehouse/` package (and `scripts/`, `infra/`)
  for every call site of `merge_current_filing_feed` and
  `current_filing_feed`. The **only** matches are the definition itself and
  its registration in protection/sharding config — there is no orchestrator
  command, loader function, or CLI handler anywhere in the repo that calls
  `merge_current_filing_feed()`. Contrast with the sibling table
  `stg_daily_index_filing`, whose write path is fully wired:
  `edgar_warehouse/application/warehouse_orchestrator.py:3670` (`_load_daily_index_for_date`)
  → `stage_daily_index_filing_loader()`
  (`edgar_warehouse/loaders/bronze_daily_index_extractors.py:15-72`, which
  parses the real `form.YYYYMMDD.idx` line format against
  `https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{q}/form.{date}.idx`,
  built in `edgar_warehouse/infrastructure/sec_client.py:166`) → `db.merge_daily_index_filings()`
  (`silver_store.py:2093`). I confirmed this parser's expected line shape
  matches the real `form.20260721.idx` file I fetched from SEC.
- This repo's own `docs/data-architecture.md:142` already flags the
  discrepancy, describing `sec_current_filing_feed` as *"Legacy/current feed
  surface **if populated**"* — hedging on exactly the thing I confirmed: it
  isn't populated.
- **Conclusion**: `sec_current_filing_feed`'s schema (accession, CIK, form,
  filing/index hrefs, `feed_published_at`) looks purpose-built to hold rows
  from an Atom/RSS-style feed like `getcurrent`, but nothing in this repo
  produces those rows today. Using it as the IPO-detection source would
  require **new ingestion code** (a loader that polls
  `browse-edgar?action=getcurrent&type=...` or a form-filtered daily-index
  pass and calls the existing `merge_current_filing_feed`), not a wiring fix
  to something already running. Alternatively, the already-working
  `stg_daily_index_filing` path could be filtered for `S-1`/`S-11`/`F-1`/
  `EFFECT`/`424B4` form types with no new ingestion code at all — only new
  query logic — at the cost of the daily-index's ~end-of-day latency (see
  Q3) instead of the `getcurrent` feed's minutes-level latency.

---

## Correction to the prior guess in TODOS.md

TODOS.md's "Fix approach" section (line ~51-55) hypothesized: *"the IPO-
detection source (SEC's daily/current filing feed already ingested via
`sec_current_filing_feed`) looks like the natural signal — a first-ever
S-1/424B4/effective registration for a CIK not yet in
`sec_company_sync_state`."*

What I found confirms part of this and corrects part of it:

- **Confirmed**: the general shape of the signal — first-ever registration
  (`S-1`/`S-11`/`F-1`) followed by `EFFECT` and `424B4`/`424B3` pricing — is
  the right pattern to watch, since SEC exposes no more direct signal (Q1).
- **Wrong / needs correction**: `sec_current_filing_feed` is **not
  "already ingested"** — I found no code path anywhere in this repo that
  populates it (Q5). The TODOS.md phrase "already ingested via
  `sec_current_filing_feed`" is factually incorrect as of this investigation
  and should be corrected before anyone plans against it as if it's live
  data.
- **Also worth correcting**: `sec_company_sync_state` (grepped across
  `edgar_warehouse/mdm/`, `silver_store.py`, `scripts/ops/`) is a
  warehouse-pipeline processing tracker — per-CIK bootstrap/sync progress,
  `tracking_status`, pagination counts, `next_sync_after` — not a SEC-sourced
  company-status or listing-status table. "Not yet in
  `sec_company_sync_state`" is a reasonable proxy for "not yet in our
  universe" (i.e., useful for the *seed-universe* half of the TODO), but it
  is an internal bookkeeping table, not an EDGAR data source, and has no
  bearing on whether a company has actually IPO'd — worth being precise
  about in any future design doc so the two concerns (SEC signal vs. our own
  tracking state) aren't conflated.

## Recommendation for this repo

For the TODOS.md "pick up new IPOs as they start trading" requirement:

1. **Primary signal**: poll SEC's "Latest Filings" feed
   (`https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=<FORM>&output=atom`)
   filtered separately for `type=S-1`/`type=S-11`/`type=F-1` (pending
   registration — earliest possible signal, per Q4) and `type=EFFECT` /
   `type=424B4` (pricing/trading-imminent — the promote-to-active trigger).
   Expected latency: minutes from EDGAR acceptance (per SEC's own FAQ, "1-3
   minutes... as close to real time as possible").
2. This requires **new ingestion code** — there is no existing loader for
   this feed in the repo. The existing `sec_current_filing_feed` table's
   schema is a reasonable landing spot for the parsed rows (it already has
   `accession_number`, `cik`, `form`, `filing_href`, `feed_published_at`) and
   its write method (`merge_current_filing_feed`) already exists — only the
   fetch/parse/call wiring needs to be added, analogous to
   `_load_daily_index_for_date` / `stage_daily_index_filing_loader` for the
   daily-index path.
3. **Fallback/cheaper option**: if minutes-level latency isn't actually
   required and a daily cadence is acceptable (the TODOS.md ask is "daily
   schedule" for the seed-universe refresh generally), extend the
   already-working, already-wired `stg_daily_index_filing` daily-index
   ingestion (`_load_daily_index_for_date` in
   `warehouse_orchestrator.py:3670`) with a query filtered to
   `S-1`/`S-11`/`F-1`/`EFFECT`/`424B4` form types feeding the daily
   seed-universe refresh job. This reuses fully-tested, currently-running
   code and costs only end-of-day latency (~10 PM ET the same day) instead of
   near-real-time — likely an acceptable tradeoff for a "daily refresh," and
   avoids building and maintaining a second (currently-nonexistent) ingestion
   path.
4. **Do not rely on `company_tickers.json`/`company_tickers_exchange.json`**
   as the IPO-detection trigger — SEC does not commit to a refresh cadence
   for either file (its own FAQ says "periodically... do not guarantee
   accuracy or scope"), and the two files were observed to be on visibly
   different refresh schedules (a day vs. about a week stale) at the same
   sampling moment. They remain fine as the bulk source for the existing
   `seed_universe_loader` full-universe seed, just not as the fast-path IPO
   trigger.

## Sources fetched directly (all accessed 2026-07-22 unless noted)

- `https://www.sec.gov/search-filings/edgar-application-programming-interfaces` — EDGAR APIs overview, "Update Schedule" section.
- `https://www.sec.gov/os/webmaster-faq` — redirects (HTTP 301) to `https://www.sec.gov/about/webmaster-frequently-asked-questions` (confirmed via `curl -L`); sections `#lag`, `#fast-access`, `#ticker-cik`.
- `https://www.sec.gov/files/company_tickers.json` — fetched with headers; `Last-Modified: Tue, 21 Jul 2026 20:44:01 GMT`.
- `https://www.sec.gov/files/company_tickers_exchange.json` — fetched with headers; `Last-Modified: Wed, 15 Jul 2026 20:47:11 GMT`.
- `https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/index.json` — real directory listing with per-file `last-modified` timestamps.
- `https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/form.20260721.idx` — real daily form-type index, inspected for `S-1`, `S-1/A`, `F-1`, `F-1/A`, `EFFECT`, `424B3`, `424B4` entries.
- `https://data.sec.gov/submissions/CIK0002131350.json` — real CIK submissions history (B&R Technology Merger Corp.), used for the DRS→S-1→EFFECT→424B4 timeline and `tickers`/`exchanges` field behavior.
- `https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=424B4&output=atom` — live "Latest Filings" Atom feed, filtered by form type.
- `https://efts.sec.gov/LATEST/search-index?...forms=424B4&startdt=2026-07-21&enddt=2026-07-21` — EDGAR full text search API, confirmed indexing of prior-day `424B4` filings by next-morning query.

## Code read directly in this repo

- `edgar_warehouse/application/warehouse_orchestrator.py:141-187` (`run_seed_universe_command`), `:47` (import of `seed_universe_loader`).
- `edgar_warehouse/loaders/bronze_reference_extractors.py:1-59` (`seed_universe_loader` — confirms it parses exactly `company_tickers.json`'s dict-of-entries schema and `company_tickers_exchange.json`'s `fields`/`data` schema).
- `edgar_warehouse/silver_store.py:119-134` (`sec_current_filing_feed` DDL), `:1669-1725` (`merge_current_filing_feed`/`get_current_filing_feed`), `:307-326` (`stg_daily_index_filing` DDL), `:2093-2154` (`merge_daily_index_filings`/`get_daily_index_filings`), `:487-501` (`sec_company_sync_state` DDL).
- `edgar_warehouse/loaders/bronze_daily_index_extractors.py:15-72` (`stage_daily_index_filing_loader` — real `form.idx` line parser).
- `edgar_warehouse/application/warehouse_orchestrator.py:3670-3802` (`_load_daily_index_for_date` — the fully-wired daily-index ingestion path).
- `edgar_warehouse/infrastructure/sec_client.py:156-166` (`build_company_tickers_url`, `build_company_tickers_exchange_url`, daily-index URL builder).
- `edgar_warehouse/silver_protection.py:100-101,216-224` and `edgar_warehouse/silver_support/sharded_reader.py:64,75-83` (table registration for `sec_current_filing_feed`, `stg_daily_index_filing`, `sec_company_sync_state` — confirms registration without a producer for the first table).
- `docs/data-architecture.md:137-142` (existing doc already hedges `sec_current_filing_feed` as "if populated").
- `TODOS.md:8-58` (the sourcing entry this research was requested for).
