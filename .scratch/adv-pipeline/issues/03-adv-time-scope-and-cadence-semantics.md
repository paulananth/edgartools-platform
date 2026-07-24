# 03 — ADV Time-Scope and Cadence Semantics

Type: grilling
Status: claimed
Blocked by: none
Blocks: 06

## Question

IAPD bulk data is a monthly full point-in-time roster snapshot (current
firms + their current filing state) with no year-window concept — unlike
13F/proxy/8-K relationship types, which have explicit lookback windows
(`THIRTEENF_AGENT_LOOKBACK_MONTHS`, `PROXY_AGENT_LOOKBACK_YEARS`, etc.). The
original ask ("run ADV data for 1 year") doesn't map onto this shape.
Decide, independent of ticket 01/02's parser findings:

1. What should `load_history` (baseline/backfill) actually fetch for ADV —
   just the current snapshot (single full-roster fetch, since there is no
   historical roster to backfill), or something else?
2. What should `daily_incremental` do for ADV, given SEC only republishes
   monthly — a monthly-cadence idempotent check (skip cleanly if the current
   month's snapshot was already ingested), a fixed-day-of-month trigger, or
   a daily "did a new month's files appear yet" poll that no-ops on cache
   hit (mirroring the artifact-throttle 5-whys pattern already in
   CLAUDE.md — no-op paths must not carry needless cost)?
3. What is the idempotency key for a `dataset_period` (e.g. snapshot
   publication month) — and does re-running against the same
   `dataset_period` need to detect and ingest *changes* (a firm's ADV
   amendment within the same monthly snapshot cycle), or is each
   `dataset_period` treated as fully immutable once ingested (matching the
   platform's general SEC-data-is-additive-and-immutable convention in
   CLAUDE.md)?
4. Does "Exempt Reporting Advisers" get treated identically to "Registered
   Investment Advisers" for cadence/scope purposes, or does anything differ?

## Answer

(pending)
