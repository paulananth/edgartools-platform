# 03 — ADV Time-Scope and Cadence Semantics

Type: grilling
Status: resolved
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

**Revised mid-resolution:** ticket 01 found the premise ("full point-in-time
roster snapshot, no year-window concept") was wrong — the authoritative
per-fund source (`advFilingData`) is actually a monthly filing-activity
delta with historical archives back to 2000-10-19. Q1 and Q2 below were
re-asked under the corrected model before being finalized.

1. **`load_history` fetches a rolling ~13-month window only, not deeper
   history.** Union the last ~13 monthly `advFilingData` deltas (dedup by
   CRD/FilingID, keep latest per firm) to reconstruct full current
   adviser/fund coverage — sufficient since RIAs must reaffirm Form ADV at
   least annually. The two static pre-2025 archives (2000-2011, 2011-2024)
   are explicitly **not** backfilled: no identified consumer for multi-year
   ADV filing history, mirroring the exact reasoning CLAUDE.md already
   applied narrowing 13F (3y→1y→1 quarter) and proxy (5y→1y) to
   current-state-only. Ticket 02 owns verifying the 13-month figure is
   airtight (not just a heuristic) before it's used as a hard window size,
   and owns the mechanical rolling-window/dedup design itself.
2. **`daily_incremental` runs daily, gated by a local `dataset_period`
   already-ingested check — unchanged by the delta-vs-snapshot
   correction.** The idempotency mechanics (check silver locally first,
   zero network cost on a hit; only scrape/fetch when the current month
   isn't yet ingested) don't depend on whether a period's payload is a full
   snapshot or a partial delta — that distinction only affects what a
   period's ingested rows *represent* (ticket 02's rolling-window concern),
   not when to check for a new one.
3. **Each `dataset_period` (one calendar month) is fully immutable once
   ingested.** A published monthly delta file represents a closed window of
   filing activity that already happened; SEC doesn't retroactively rewrite
   it — a firm's next amendment shows up in a *later* month's delta, not a
   mutation of an earlier one. Matches the platform's general SEC-data-is-
   additive-and-immutable convention (CLAUDE.md). Re-running against an
   already-ingested period is a pure no-op, same as bronze filing
   idempotency elsewhere in the platform.
4. **ERA and RIA get identical cadence/scope handling.** Ticket 01 found
   both `IA_`- and `ERA_`-prefixed file variants inside the same monthly
   `advFilingData` ZIP, published together on the same cadence. ERAs filing
   fewer Form ADV items only affects which columns are populated, not the
   fetch/window/idempotency mechanics.
