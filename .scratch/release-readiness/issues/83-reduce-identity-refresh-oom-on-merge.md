Type: task
Status: open

## Question

`daily-incremental-ticket77-livemeasure-1785794199` (started 2026-08-03
17:56:42-04:00 to get ticket 77/78's post-fix live throughput measurement)
failed at `ReduceIdentityRefresh` before ever reaching `RunWarehouseTask`'s
artifact-fetch stage -- the container was OOM-killed (exit 137,
`OutOfMemoryError: container killed due to memory usage`) on task
`arn:aws:ecs:us-east-1:690839588395:task/edgartools-prod-warehouse/7ea08bf3fa024d89ad57c7477dca7638`,
task definition `edgartools-prod-medium:122` (4096MB), running command
`reduce-identity-refresh --run-id daily-incremental-ticket77-livemeasure-1785794199 --max-attempts 3`.
Root-cause and fix (or re-size) the memory ceiling for this step.

## Evidence (live, 2026-08-03)

Full CloudWatch log for the task (`warehouse-medium/edgar-warehouse/7ea08bf3fa024d89ad57c7477dca7638`)
is only 12 lines -- the process died mid-merge with no further output:

```
identity_refresh_attempt_started (attempt 1/3)
identity_refresh_baseline_read_completed (canonical_exists=true, byte_size=1,253,847,040 (~1.17GB), etag=7189712c3dccab86ef439488a1e19bc3)
identity_refresh_candidate_merge_started (batch_id=reference, candidate_index=0, candidate_count=4)
silver_table_merge_started: sec_company                  -> merged (39,716 unchanged)
silver_table_merge_started: sec_company_address           -> merged (79,432 unchanged)
silver_table_merge_started: sec_company_former_name       -> merged (8,269 unchanged)
silver_table_merge_started: sec_company_submission_file   -> merged (3,077 unchanged)
silver_table_merge_started: sec_company_filing            -> [container OOM-killed here, no completion event]
```

The `silver_table_merge_started`/`silver_table_merged` event pairs are
`merge_candidate_into_canonical`'s own instrumentation (ticket 82) --
confirms `reduce_identity_refresh` (`identity_refresh_publication.py`)
calls the exact same merge path `_publish_silver_database_if_remote` uses,
walking `PROTECTED_TABLE_REGISTRY` in declaration order. It died on the
6th table (`sec_company_filing`), on the very first of 4 candidates
(the "reference" baseline merge, before any of the 3 real batch deltas).

## Suspected root cause (not yet confirmed -- needs the same rigor as the
resolved "Gold-build memory / daily_incremental OOM" 5-whys in CLAUDE.md)

That CLAUDE.md entry root-caused a sibling problem in the *gold build* path
(`build_gold()` materializing all ~24 gold tables in memory at once) and
fixed it by streaming table-by-table instead. `merge_candidate_into_canonical`
(`silver_protection.py`) has a related but distinct shape worth checking:
`_delta_rows_as_dicts`/`_matching_canonical_rows_as_dicts` materialize a
table's differing rows as Python `dict` lists (not a DuckDB-native
set-based operation) before the per-row `_insert_row`/`_update_row` Python
loop -- flagged as a structural concern (not yet acted on) in an earlier
`/gof-refactor-reviewer` pass this session on this exact function
(pipeline-throughput-architecture ticket 05), which found the *measured*
per-candidate cost (187.9s / 1.4% of a normal run) too low to justify
restructuring at the time. `sec_company_filing` is a large table (the
`fact_filing_activity`/`dim_filing` gold-side sibling was ~3.26M rows per
the gold-build 5-whys) -- worth checking whether this run's row-count for
`sec_company_filing` at the current canonical size (1.17GB, presumably
grown since the ~1.021GB cited in ticket 05's review) crossed a threshold
that a 4096MB `medium` task can no longer hold alongside the rest of the
merge's working set. Also worth checking whether `edgartools-prod-medium`
is even the right task family for `reduce-identity-refresh` -- the
gold-build fix moved `daily_incremental`/`bootstrap`/`full_reconcile`/
`gold_refresh`'s `RunWarehouseTask` step onto the 8192MB `large` family,
but `reduce-identity-refresh` runs as its own separate ECS task
(`ReduceIdentityRefresh` state) and was not touched by that fix -- unclear
whether it was ever evaluated against `large`'s bump at all.

## Why this blocks other work

This is the second consecutive `daily-incremental` execution
(`ticket77-livemeasure`, started specifically to get
[ticket 77](77-implement-artifact-fetch-concurrency.md)/
[ticket 78](78-implement-shared-submissions-fetch-concurrency.md)'s live
throughput measurement) that failed before reaching `RunWarehouseTask`'s
artifact-fetch stage at all -- ticket 77/78's "Done when" item 5 (live
measurement) remains genuinely unobtained. Also blocks
[ticket 82](82-add-silver-merge-per-table-started-event.md)'s own live
verification the same way (it needs a `RunWarehouseTask` execution past
the deploy, and this run never got there either) and
[tickets 49/61/63](49-implement-bounded-daily-identity-refresh-schedule.md)'s
shared "immutable-image production evidence" gate.

## Done when

Root-caused (confirmed, not assumed) why `reduce-identity-refresh` OOM'd
specifically on `sec_company_filing`'s merge, a fix or re-size decided and
applied, and a fresh `daily-incremental` execution completes
`ReduceIdentityRefresh` without OOM.
