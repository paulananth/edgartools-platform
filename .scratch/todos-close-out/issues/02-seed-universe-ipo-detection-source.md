# 02 — Seed universe: which IPO-detection source to build?

Type: grilling
Status: resolved
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

**Decision: reuse the existing daily-index pipeline — and it turned out to
need even less than "(b)" assumed.**

Investigated the actual code before implementing: `daily-incremental`'s
`_load_daily_index_for_date` → `_seed_silver_tracking_status` already marks
*any* brand-new CIK as `"active"` the moment it files anything at all,
including a first-ever S-1 — zero form-type filtering required. This isn't
new code to write; it's an existing side effect of impacted-CIK discovery
that was never form-filtered in the first place.

**The actual gap:** nothing schedules `daily-incremental` to run. Confirmed
via `aws events list-rules` — no EventBridge rule targets it in prod. It
exists in code/infra but has to be manually invoked.

**Implementation split in two:**
1. Code: none needed for IPO detection itself (already correct).
2. Infra: add a daily EventBridge schedule invoking
   `edgartools-prod-daily-incremental`, after the daily-index file's
   expected ~6am ET availability (`sec_calendar.expected_available_at`).
   IAM role for EventBridge→SFN `StartExecution` lives in Terraform
   alongside the existing `pipeline_notifications` module pattern.
   **Not yet applied to prod** — built and PR'd, but turning the schedule
   on is a separate gated step (same two-gate discipline as Ticket 20):
   needs a green build and explicit user go, since it starts an autonomous
   recurring production job.
