# 03 — Seed universe: what signal determines a company is no longer active?

Type: grilling
Status: open
Blocked by: [Ticket 02 — Seed universe: which IPO-detection source to build?](02-seed-universe-ipo-detection-source.md)

## Question

TODOS.md's seed-universe entry requires demoting companies that are no
longer active so they stop generating candidate work, but doesn't decide
the signal source. Candidates: SEC's own company-status data (if any,
via submissions.json), a delisting feed, or an existing internal
`tracking_status` transition already used elsewhere in this pipeline.
Decide the source and how it plugs into `run_seed_universe_command` /
`sec_company_sync_state`.

**Why this is blocked by Ticket 02:** the "new IPO" signal (Ticket 02) and
the "no longer active" signal (this ticket) are the two halves of the same
seed-universe refresh redesign — both feed `run_seed_universe_command` /
`sec_company_sync_state`, and both need to land on the same daily-refresh
cadence TODOS.md calls for. Ticket 02's two candidates carry directly over
here:

(a) If Ticket 02 picks the `getcurrent` "Latest Filings" feed (new
    ingestion, minutes-level latency), the natural symmetric choice for
    "no longer active" is the same feed's delisting/Form 25 filings, so
    both signals ride one new ingestion path and one poll loop instead of
    two.
(b) If Ticket 02 picks filtering the existing `stg_daily_index_filing`
    daily-index path (no new ingestion code, end-of-day latency), the
    symmetric choice is filtering that same daily index for Form 15/Form 25
    (deregistration/delisting) — reusing `_load_daily_index_for_date`
    rather than adding a second detection mechanism.

Deciding Ticket 02 first fixes which of these two shapes this ticket
inherits, so this ticket should resolve as "apply the Ticket 02 pattern to
the inactive-company signal" rather than independently re-litigating
new-ingestion-vs-filter.

## Answer

(resolved on close)
