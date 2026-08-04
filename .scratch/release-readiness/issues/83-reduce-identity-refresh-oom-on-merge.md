Type: task
Status: in_progress

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

## Root cause (confirmed live, not inferred, 2026-08-03)

Reproduced directly: downloaded the real canonical `silver.duckdb`
(~1021.8MB) and the real `reference_snapshot.duckdb` from the failed run's
own S3 paths, ran `reduce_identity_refresh`'s merge path inside a
`docker run --memory=4096m` container against the actual locally-built
warehouse image (matching prod's `medium` task's 4096MB Fargate cgroup
ceiling exactly). It died silently at the identical point --
`sec_company_filing`'s merge, zero further output -- matching prod's
CloudWatch log exactly. Local macOS `/usr/bin/time -l` RSS measurements
(2.0-2.35GB peak) had NOT shown this, because macOS's own RSS accounting
doesn't reflect Fargate's cgroup memory accounting; the constrained-container
repro was necessary to actually see the failure.

Mechanism: ticket 76's earlier fix (`verified_bytes: dict[str, bytes]`, all
4 candidates' verified inputs held in memory for the reducer's entire
lifetime, to avoid re-fetching from S3 across retries) stacks with a fresh
per-attempt `baseline_payload` (a full `read_bytes()` of the growing
canonical file, re-read every attempt) plus the merge's own DuckDB working
set for a 6.8M-row-class table. None of these individually is enormous, but
held simultaneously they push peak memory past the 4096MB ceiling. This is
a distinct mechanism from the sibling gold-build OOM (CLAUDE.md, "Gold-build
memory / daily_incremental OOM") -- that one was full-materialization of
~24 gold tables in one dict; this one is retry-durability bytes plus a
per-attempt baseline re-read stacking on top of the merge's own footprint.

## Fix (implemented, unit-tested, not yet live-verified)

1. **Structural**: `identity_refresh_publication.py`'s
   `reduce_identity_refresh` no longer holds verified candidate bytes in a
   Python dict for the call's lifetime. Verified inputs are now written
   once to a `tempfile.mkdtemp()`-backed cache directory
   (`verified_paths: dict[str, Path]`) and read from disk on each retry
   attempt instead -- preserves ticket 76's original goal (no re-fetch from
   S3 across retries) while eliminating the multi-gigabyte in-memory
   stacking. Cache directory is removed via `try/finally: shutil.rmtree`
   on both success and failure paths. Two new regression tests
   (`tests/unit/test_identity_refresh_publication.py`) assert the cache
   directory is created and cleaned up in both cases; confirmed via
   `git stash` to fail before the fix (no cache dir ever created) and pass
   after.
2. **Belt-and-suspenders resize**: `ReduceIdentityRefresh`'s ECS task moved
   from `wh_medium_arn` (4096MB) to `wh_large_arn` (8192MB) in
   `deploy-aws-application.sh`, matching the precedent set by the
   gold-build-memory-reliability fix for `RunWarehouseTask`. New
   architecture test
   (`test_reduce_identity_refresh_runs_on_the_large_task_definition`,
   `tests/architecture/test_daily_identity_refresh_state_machine.py`)
   asserts this; confirmed via `git stash` to fail before and pass after.

Full suite (`tests/unit tests/application tests/architecture tests/mdm`):
1724 passed, 4 skipped, 35 subtests passed -- only the one pre-existing,
unrelated `test_go_live_wizard.py::test_plan_prints_preview_only_aws_ordered_commands`
failure (stale AWS profile string in a test fixture, unrelated to this
change).

**Not yet done**: live prod verification (rebuild + push the warehouse
image, redeploy via `deploy-aws-application.sh --env prod`, trigger a fresh
`daily-incremental` execution and confirm `ReduceIdentityRefresh` completes
without OOM) is still outstanding -- deferred pending explicit confirmation
per this workstream's live/destructive-action convention. That same run
would also finally obtain [ticket 77](77-implement-artifact-fetch-concurrency.md)/
[ticket 78](78-implement-shared-submissions-fetch-concurrency.md)'s
still-missing live throughput measurement, since it needs
`ReduceIdentityRefresh` to complete before `RunWarehouseTask` even starts.
