# 03 — Seed universe: what signal determines a company is no longer active?

Type: grilling
Status: resolved
Blocked by: [Ticket 02 — Seed universe: which IPO-detection source to build?](02-seed-universe-ipo-detection-source.md) (resolved)

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

**Decision: Form 15 deregistration, filtered from the same daily-index
pipeline Ticket 02 reuses** — option (b)'s pattern, narrowed to Form 15
only, not Form 15+25.

Form 25 (exchange delisting) was deliberately excluded: it only means a
company left an exchange, not that it stopped filing with SEC — many
Form-25'd companies keep filing periodic reports as OTC stocks. Demoting on
Form 25 alone risked silently dropping tracking on companies still actually
filing. Form 15 is the SEC-recognized end of reporting obligations.

**Implemented** (not just decided — code + tests, merged):
`_ciks_filing_form15()` scans daily-index rows for domestic
(15-12B/15-12G/15-15D) and foreign-private-issuer (15F-12B/15F-12G/
15F-15D) variants; `_demote_deregistered_ciks()` sets
`tracking_status = "deregistered"`, wired into `_capture_bronze_raw`'s
daily-incremental branch right before `_filter_ciks_to_universe`, so a
demoted CIK is excluded from that same run's bootstrap selection.

Surfaced and fixed a real landmine along the way:
`_apply_submission_snapshot_to_silver`'s fallback normalized any
unrecognized `tracking_status` back to `"active"` — `"deregistered"` would
have been silently un-demoted the next time any code path (ad-hoc resync,
`targeted-resync`) reprocessed that CIK's submissions. Added to the
allowlist.

Ships once daily-incremental actually runs regularly, same as Ticket 02 —
tracked there, not duplicated here.
