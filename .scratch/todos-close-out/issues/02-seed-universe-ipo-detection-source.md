# 02 — Seed universe: which IPO-detection source to build?

Type: grilling
Status: open
Blocked by: (none)

## Question

Per `docs/sec-edgar-ipo-detection.md` (researched 2026-07-22), two real
options exist for detecting new IPOs to add to the seed universe:

(a) New ingestion against SEC's `getcurrent` "Latest Filings" feed —
    minutes-level latency, requires new loader code, lands in the existing
    but currently-unused `sec_current_filing_feed` schema.
(b) Filter the already-working `stg_daily_index_filing` daily-index path
    (`_load_daily_index_for_date`) for S-1/S-11/F-1/EFFECT/424B4 form
    types — no new ingestion code, ~end-of-day latency.

Decide which to build, given the requirement is a "daily refresh" cadence
(TODOS.md), not necessarily real-time.

## Answer

(resolved on close)
