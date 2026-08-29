# 48 — Add a per-candidate progress counter to gated discovery

**What to build:** One periodic log line in
`run_gated_discovery_for_business_date` (`edgar_warehouse/application/workflows/drive_filing_discovery.py`)
reporting candidates processed so far against the known total, so an
operator watching a live run can compute a real completion percentage
without reasoning about SQL-statement counts.

**Blocked by:** None — can start immediately.

**Status:** resolved

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

- [x] `run_gated_discovery_for_business_date` logs the total candidate
  count once at start.
- [x] `run_gated_discovery_for_business_date` logs a running
  processed-count at a reasonable cadence (time- or count-based, not one
  line per candidate — avoid multiplying log volume by the same factor
  this ticket is trying to make legible).
- [x] A unit test asserts both new log events fire with the right field
  shape, mirroring the existing `silver_apply_progress` test coverage.

## Answer

`run_gated_discovery_for_business_date` now emits `gated_discovery_started`
(`candidate_count`, `business_date`, `source_family`) once the sealed
manifest is built, then `gated_discovery_progress` (`processed` /
`candidate_count`, same identity fields) on a bounded cadence: every 100
candidates, every 30 seconds, and always on the last candidate. Logging
stays in the workflow; `drive_discovery_manifest` only gained an optional
`on_progress(processed, candidate_count)` callback so the per-candidate
loop can report without owning CloudWatch event shape.

Events go through the existing `_emit_pipeline_event` stderr JSON path
(`silver_apply_progress`'s shape). `business_date` / `source_family` are
on both events because Ticket 46's in-process caller can run this once
per date inside a larger daily-incremental task.

Tests: `test_gated_discovery_emits_started_and_progress_events` (live
command path, two sealed daily-index rows) and
`test_gated_discovery_progress_is_not_emitted_per_candidate` (cadence
helper: count tick, final tick, time tick, and the silent in-between).
