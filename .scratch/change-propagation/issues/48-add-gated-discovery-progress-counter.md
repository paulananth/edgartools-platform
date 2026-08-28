# 48 — Add a per-candidate progress counter to gated discovery

**What to build:** One periodic log line in
`run_gated_discovery_for_business_date` (`edgar_warehouse/application/workflows/drive_filing_discovery.py`)
reporting candidates processed so far against the known total, so an
operator watching a live run can compute a real completion percentage
without reasoning about SQL-statement counts.

**Blocked by:** None — can start immediately.

**Status:** open

## Question

Found live 2026-08-28 while watching Ticket 46's live-prod verification
run. The gated-capture path logs one structured event per SQL statement
(`mdm_sql_started`/`mdm_sql_completed`, tagged with the table touched) but
never logs a candidate-level progress marker. Each candidate triggers a
variable number of SQL round trips (observed: not a fixed ratio), so
"count of `source_fetch_decision`-tagged queries so far" cannot be turned
into an accurate percentage — confirmed the hard way this session: a
query-count-based estimate exceeded the real, verified total (4,491 sealed
daily-index rows for the date) well before the run actually finished.

The real total is already knowable up front — `_load_sealed_discovery_rows`
returns the full candidate list before the per-candidate loop starts — so
the fix is small: log the total once at the start (e.g.
`gated_discovery_started` with a `candidate_count` field), and log a
running count every N candidates or every N seconds (e.g.
`gated_discovery_progress` with `processed`/`candidate_count`), mirroring
the existing `silver_apply_progress` event's shape
(`applied`/`cik_count`/`rows_written` fields) already used elsewhere in
this same codebase for exactly this purpose.

**Impact today:** low — this blocked nothing, it only made a live run
harder to monitor externally. Worth fixing before the next long gated-
discovery run someone needs to babysit, especially once broader source
families are cut over (Ticket 27) and these runs get both more frequent
and larger.

## Acceptance

- [ ] `run_gated_discovery_for_business_date` logs the total candidate
  count once at start.
- [ ] `run_gated_discovery_for_business_date` logs a running
  processed-count at a reasonable cadence (time- or count-based, not one
  line per candidate — avoid multiplying log volume by the same factor
  this ticket is trying to make legible).
- [ ] A unit test asserts both new log events fire with the right field
  shape, mirroring the existing `silver_apply_progress` test coverage.
