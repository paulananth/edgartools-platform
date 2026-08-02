# Batch merge_daily_index_filings inserts instead of per-row autocommit

Type: task
Status: resolved

## Question

Why did `daily-incremental-ticket67-verify-1785709701`'s `ComputeIdentityRefreshWindow`
step spend ~53 seconds per daily-index file (7-day lookback = ~5-6 minutes total) when
each SEC download itself completed in 100-250ms, and how should it be fixed?

## Root cause

Not a caching gap: `compute-identity-refresh-window` in `daily` mode intentionally calls
`_load_daily_index_for_date(..., force=True)` for every day in the lookback window
(`warehouse_orchestrator.py:2416-2424`) — deliberate revalidation behavior from the
earlier "Daily accession-expansion" fix (CLAUDE.md), not something to cache around.

The actual cost was entirely in `merge_daily_index_filings` (`silver_store.py`), which
looped over every row in a downloaded daily-index file and ran one
`INSERT ... ON CONFLICT DO UPDATE` statement per row with no explicit transaction, so
DuckDB autocommitted each statement individually. Downloaded the real
`form.20260728.idx` SEC serves for that date to confirm: **6,029 filing rows** (SEC
daily index files list one line per filer/form on a business day, commonly several
thousand). Measured against real prod data: 53s / 6,028 rows ≈ 8.8ms/row — the
signature of per-statement autocommit overhead, not query cost or network cost.

Isolated benchmarking during investigation showed a plain `BEGIN TRANSACTION`/`COMMIT`
wrap alone was insufficient (3,000 rows: 15.4s unwrapped → 5.7s wrapped) — DuckDB's
Python binding still pays meaningful per-`execute()` parse/plan/bind overhead even
inside one transaction. The effective fix needed to be set-based, not just
transaction-batched.

This is the same structural bug ticket 67 fixed in `silver_protection.py` (a per-row
Python loop instead of a batched/set-based DuckDB operation), independently present here
in a different file and a different pipeline stage — `merge_daily_index_filings` was
never touched by that fix. It's also the same pattern this file's own `merge_filings`
already had to fix previously (see the doc comment on `merge_filings`, "384K rows took
577s"), via a bulk-staging helper (`_merge_rows_bulk`) — `merge_daily_index_filings`
just never got the same treatment.

## Fix

`edgar_warehouse/silver_store.py::merge_daily_index_filings`: stage all rows in one shot
via a registered Arrow table (`pa.table` + `conn.register`, the same primitive
`_merge_rows_bulk`/`merge_filings` already use elsewhere in this file) into a reusable
temp staging table, then apply the upsert as a single set-based
`INSERT ... SELECT ... ON CONFLICT DO UPDATE` statement. `QUALIFY ROW_NUMBER() OVER
(PARTITION BY business_date, accession_number ORDER BY seq DESC) = 1` dedupes same-key
rows within one batch, keeping the highest-`seq` (list-order-last) occurrence — matching
the original loop's implicit last-write-wins semantics exactly (every column in the
original `ON CONFLICT DO UPDATE SET` clause was already last-write-wins; no
first-insert-only columns like `merge_filings` has, so the simpler single-statement form
was sufficient here — no need for `_merge_rows_bulk`'s two-phase first/last split).
Return value (`len(rows)`) preserved exactly — the original loop also incremented
`count` unconditionally per input row regardless of insert-vs-update, not per distinct
key.

## Validation

- Isolated DuckDB benchmarking (3,000 synthetic rows) before picking an approach: no
  transaction 9.6s; `BEGIN`/`COMMIT`-wrapped loop 5.7s (insufficient); Arrow-register +
  set-based upsert 0.02-0.12s.
- Real end-to-end run against the actual `form.20260728.idx` file SEC serves (downloaded
  live, 6,029 rows, the same file the stalled verification run fetched): **0.137s**
  merged (fresh insert) and **0.074s** re-merged (all-update path, exercising
  `ON CONFLICT DO UPDATE`) — versus the 53s this exact file took live in prod under the
  old code. Confirmed final row count identical (4,162 distinct `(business_date,
  accession_number)` keys out of 6,029 lines — the daily index format legitimately lists
  some accessions on multiple lines, e.g. multi-registrant filings; both old and new code
  collapse to the same final state via the same primary key, so this is not a regression)
  and that a second merge correctly updates `sync_run_id` on every row (last-write-wins
  preserved).
- Two new tests added (`tests/unit/test_daily_index_filing_merge.py`): upsert-updates-
  existing-row correctness check, and a 3,000-row batch timing regression guard
  (`< 5.0s`, generous CI headroom — the old unbatched code would take ~15-25s at this
  volume, so this reliably catches a reintroduction of the per-row autocommit pattern).
- Full suite: `tests/unit tests/application tests/architecture tests/mdm` — 1678 passed,
  4 skipped, 1 pre-existing unrelated failure (same
  `test_go_live_wizard.py::test_plan_prints_preview_only_aws_ordered_commands` already
  documented as pre-existing/environment-dependent in [ticket 67](67-fix-authority-column-false-positive-conflicts.md)).

Found while watching the live `daily-incremental-ticket67-verify-1785709701` production
run used to validate ticket 67 — `ComputeIdentityRefreshWindow` was visibly still slow
(SEC calls ~53s apart) even after that fix deployed, prompting this second investigation.

## Done when

Done — fix implemented, validated against real production data end-to-end, regression
tests added, full suite green modulo the one pre-existing unrelated failure. Not yet
deployed to prod as of this entry; needs the same build/deploy cycle as ticket 67 before
its effect shows up in a live `ComputeIdentityRefreshWindow` run.
