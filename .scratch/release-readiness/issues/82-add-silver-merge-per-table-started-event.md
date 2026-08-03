Type: task
Status: resolved

## Question

`merge_candidate_into_canonical` (`edgar_warehouse/silver_protection.py`) only
logs a table's merge on *completion* (`silver_table_merged`). Add a matching
*started* event so a slow or stuck table can be named directly while it's
happening, instead of only narrowed down after the fact from the surrounding
completion events.

## Why (found live, 2026-08-03)

While watching `daily-incremental-ticket74-repair-verify-1785752569`'s
`RunWarehouseTask`, its `silver_publish` step logged 4 small tables merging
in the first few seconds (`sec_company`, `sec_company_address`,
`sec_company_former_name`, `sec_company_submission_file`), then produced
**zero log output for ~92 minutes** before the step finally exited cleanly
(exit code 0). CPU/ContainerInsights metrics confirmed the task was actively
working the whole time (not hung), and no S3 write activity was expected or
observed during that window either (`merge_candidate_into_canonical` only
writes to S3 once, at the very end, via stage-then-promote) — so there was
genuinely no signal anywhere to say which of the remaining ~27 protected
tables it was on. Given the run's unusually large candidate delta (full
~10,491-CIK active universe, not a normal ~500-CIK batch) and the size of
tables further down `PROTECTED_TABLE_REGISTRY` (`sec_raw_object`,
`sec_thirteenf_holding` at 6.8M rows in gold), the 92 minutes was plausibly
spent on one specific big table — but that was a guess, not a fact, and
stayed a guess even after the step succeeded.

This is the same shape of gap as
[ticket 64](64-add-identity-refresh-reducer-progress-logging.md) (the
identity-refresh reducer emitting zero log output for its entire runtime),
found independently in a different code path.

## Resolution

Added `_emit_table_merge_started_event(table_name)` to
`edgar_warehouse/silver_protection.py`, paired with the existing
`_emit_table_merge_event` completion event — same `event`-keyed JSON logging
convention this codebase already uses elsewhere (`gold_models.py`'s
`gold_table_started`/`gold_table_completed`). Fired once per table
immediately after confirming the candidate has data for it (i.e. right
before the potentially expensive schema reconciliation, the anti-join delta
query, and the per-row Python conflict-resolution loop), so every table that
does real work now brackets its own duration with a `silver_table_merge_started`
line before it and a `silver_table_merged` line after — including the
provenance-filtered-only fast path, which already emitted a completion event
and now gets a matching start. Tables the candidate has no data for still
emit neither event, unchanged.

New test
`test_merge_emits_a_started_event_before_the_completed_event_per_table`
(`tests/application/test_warehouse_orchestrator_mdm.py`) captures stderr via
`capsys` against a real two-table DuckDB merge (one table with candidate
data, one without) and asserts: the started/completed pair appears in order
for the table with data, and neither event appears for the table without.
All 22 existing merge tests in that file plus the full `tests/unit` +
`tests/application` + `tests/architecture` suite (1258 passed, 4 skipped,
1 pre-existing unrelated deselect, 35 subtests) pass unchanged.

Not yet deployed — takes effect on the next warehouse image rebuild/deploy,
same as every other fix landed this session.

## Done when

Implemented, tested, full suite green. (Deploy is a separate, later step —
not blocking this ticket's resolution, consistent with how tickets 67-72/76
were tracked.)
