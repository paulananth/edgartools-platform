# 03 — Confirm gold-refresh's streaming fix is the complete story for the unscoped-load shape

Type: task
Status: resolved

## Question

`gold-refresh` runs on `large` at every one of its several call sites
(standalone `gold_refresh` workflow, and embedded in `bootstrap-full`/
`targeted-resync`/`full-reconcile`/`load_history`/`bronze_seed_silver_gold`
and others — 6+ distinct `ecs_state(wh_large_arn, "States.Array('gold-refresh'...")`
call sites in `deploy-aws-application.sh`). The gold-build-memory-reliability
map already fixed `build_gold()`'s whole-dict materialization via
`iter_gold_tables()` streaming (ticket 01) and confirmed live via
CloudWatch that `sec_thirteenf_holding`'s build no longer OOMs (ticket 03).

Confirm this is the *complete* picture for the unscoped-load shape
specifically, not just the streaming-materialization shape that map
targeted. Check:
- `write_gold_to_storage_manifest`/`write_gold_to_serving_export` (the two
  callers gold-build-memory-reliability's own notes say made "two more
  full passes over that same dict" before the streaming fix) — confirm
  both are now genuinely per-table incremental, not just the outer
  `build_gold()` call.
- Whether any single gold table's own builder function (`_build_*` in
  `edgar_warehouse/serving/gold_models.py`/`source_dimensional_export.py`)
  does an unscoped full-table read internally that the streaming fix
  wouldn't catch (streaming bounds *which tables* are held in memory at
  once, not necessarily *how much* one table's own builder reads before
  writing).
- Whether `validate_data_quality.py`'s continued use of the non-streaming
  `build_gold()` (the one remaining caller gold-build-memory-reliability's
  notes mention) is itself a live risk on `large`, or runs somewhere with
  enough headroom to not matter.

If this confirms the existing fix is complete, record that explicitly as
the answer — a confirmation is a valid, useful outcome here, not just a
new fix. If a gap is found, fix it the same way MANAGES_FUND/
INSTITUTIONAL_HOLDS were.

## Blocked by

None — can start immediately.

## Answer

Confirmed the streaming fix is genuinely complete for the real production
path, and closed one small, unrelated finding surfaced along the way. No
memory-shape fix was needed — this is a confirmation, not a new gap.

**Production caller is genuinely fully streaming, traced against current
code.** `warehouse_orchestrator.py`'s `SOURCE_EXPORT_COMMANDS` path
(lines ~688-713): `for table_name, table in iter_source_export_tables(db):`
build → `write_source_export_table_manifest_entry` (storage write) →
`db.record_gold_manifest` (per-table, idempotent upsert, not batched at
loop end — an earlier table's already-durable write survives a later
table's export failure) → `write_gold_table_to_serving_export` (Snowflake
export) → `del table`. No full-dict pass exists anywhere in this live
path — confirmed by reading the actual loop body, not inferred from
`iter_source_export_tables()`'s own docstring.

**The one real unscoped-load-shape instance (`_build_fact_adv_private_fund`)
measured with real numbers, not "it completed once."** Used
`psutil.Process().memory_info().rss` (matching tonight's MANAGES_FUND/
INSTITUTIONAL_HOLDS method, not `resource.getrusage()`) around real calls to
the actual production builder functions, against the real canonical
`silver.duckdb` (downloaded live from
`s3://edgartools-prod-warehouse-690839588395/warehouse/silver/sec/silver.duckdb`,
1.59GB, 2026-08-22):

| Builder | Path | Rows measured | RSS delta | Bytes/row |
|---|---|---|---|---|
| `_build_sec_thirteenf_holding` | DuckDB-native `_arrow(conn.execute(...))` | 6,799,919 | 756.5MB | ~111 |
| `_build_fact_adv_private_fund` | Row-oriented `_fetch_rows` → Python dicts → sort → Arrow | 394,969 | 135.7MB | ~344 |

`_build_fact_adv_private_fund`'s source table (`sec_adv_private_fund`) is
genuinely the largest table read via the row-oriented `_fetch_rows` path (8
call sites use it; the other 7 are either near-empty reference/dimension
tables — `sec_adv_office` measured 1 row live — or inherently-deduplicated
dimension tables, none within orders of magnitude of `sec_adv_private_fund`'s
scale). Its measured ~344 bytes/row is ~3x `_build_sec_thirteenf_holding`'s
per-row cost, as expected for row-oriented Python dicts vs DuckDB's native
columnar Arrow conversion — but still small in absolute terms. At the
larger, more-current row count independently measured in Ticket 02's audit
(`sec_adv_private_fund` = 1,579,876 rows in the live sharded silver, vs
394,969 in this now-stale-dated, 2026-08-18 monolith snapshot — the same
shard/monolith staleness gap Ticket 02 surfaced), extrapolated peak is
~543MB — still a small fraction of the 8192MB `large` profile, with huge
headroom relative to `sec_thirteenf_holding`'s own already-safe scale.
Reaching even half the profile's memory (4096MB, leaving headroom for
everything else running concurrently) would need ~12M rows — ~7.6x
today's largest known count. **Conclusion: real, measured, wide safety
margin — not a genuine gap, no batching fix needed today.**

**`validate_data_quality.py`'s `build_source_export(db)` usage — confirmed
genuinely unscheduled, deliberate call: leave as-is.** Repo-wide search
(`grep -rn "validate-data-quality" infra/ scripts/`) returns zero results —
not wired into any Step Functions state machine or deploy script, matching
the spec's claim exactly. Not covered by
`tests/architecture/test_source_export_commands_task_sizing.py`'s memory-
floor enforcement either, since it's not a `SOURCE_EXPORT_COMMANDS` member.
No evidence found that it's about to be scheduled/automated. Decision: (a)
leave it as-is — an operator-invoked, not scheduled, risk; no code change,
no fog entry needed.

**`serving_publish.py`'s dead wrapper — confirmed dead, deleted.**
Repo-wide search for the module name and each of its 7 individual function
names (`build_source_export`, `build_ticker_reference_table`,
`write_source_dimensional_export_to_snowflake`,
`write_source_dimensional_export_to_serving`,
`write_source_export_to_storage`,
`write_ticker_reference_to_snowflake_export`,
`write_ticker_reference_to_serving_export`) found zero callers anywhere in
the codebase — the only other reference was `test_boundaries.py`'s
allowlist for a *different* boundary rule (which functions may live where),
not evidence of an actual caller. Deleted
`edgar_warehouse/application/workflows/serving_publish.py` and removed its
now-stale entry from that allowlist. `tests/architecture/test_boundaries.py`,
`tests/unit/test_source_dimensional_export_streaming.py`,
`tests/unit/test_validate_data_quality.py`, and
`tests/architecture/test_source_export_commands_task_sizing.py` all still
pass (26 tests) after the deletion.

**Self-correction found while preparing Ticket 04 (recorded here since it
corrects Ticket 02's own resolution, not this ticket's scope):** re-reading
Ticket 04's spec surfaced that Ticket 02's conclusion on the hardcoded
`SeedUniverse` state inside `write_warehouse_mdm_gold_definition` was
incomplete. Ticket 02 correctly identified the full-canonical-hydrate cost
as out of scope (owned by `seed-universe-narrow-hydrate`), but missed that
a *separate*, already-decided question — task-profile-consolidation
tickets 06/07's `command_task_profile('seed-universe') == "medium"`
routing, already ported to `write_load_history_definition`'s own
SeedUniverse — was never ported to this state, exactly the "fixed
elsewhere, not yet ported here" pattern this whole map exists to catch.
Verified live in `command_task_profile()`'s own case statement
(`seed-universe) printf '%s\n' "medium" ;;`, with tickets 06/07's decision
comment attached). Fixed by mirroring `write_load_history_definition`'s
own pattern exactly: `write_warehouse_mdm_gold_definition` now computes
`command_task_profile("seed-universe")` (guarded to only run for
`workflow_name != "daily_incremental"`, the only case that gets a
SeedUniverse state) and routes the ECS task ARN through it instead of the
stale `wh_task_large_arn` hardcode.

Tests: new `tests/architecture/test_warehouse_mdm_gold_seed_universe_task_profile_routing.py`
(3 tests), mirroring `test_seed_universe_task_profile_routing.py`'s exact
technique (source the real function, override `command_task_profile()`
*after* sourcing, prove the override's answer — not the hardcode's — wins).
Confirmed red without the fix via `git stash` (2 of 3 failed correctly;
the third needed its own fix first — an override answering "large" for
seed-universe coincidentally matched the pre-fix hardcode's value too,
since this function only has medium/large to choose from, unlike
`write_load_history_definition`'s sibling test which has a third "small"
value available as an unambiguous flip — corrected to stub "medium"
instead, the one value that actually discriminates hardcode from routing
here). Also updated 2 existing tests in
`test_run_warehouse_task_profile_routing.py` (bootstrap's strict
`command_task_profile()` stubs) to allow the new legitimate
`seed-universe` call alongside the existing `bootstrap` call — this fix
correctly makes `write_warehouse_mdm_gold_definition` call
`command_task_profile()` with `"seed-universe"` too, which those tests'
stubs previously had no case for.

**This correction should be treated as amending Ticket 02's Answer** —
Ticket 02's `SeedUniverse` finding is now: fixed (routed through
`command_task_profile()`), not "out of scope." The underlying streaming-
hydrate question Ticket 02 correctly deferred to `seed-universe-narrow-
hydrate` is unaffected and still deferred.

Full repo suite: 2328 passed, 4 skipped, only the 2 pre-existing unrelated
`test_bootstrap_dbt_snowflake_secret.py` failures. Not yet deployed —
this ticket's mandate is investigate-and-fix in the codebase; deployment
is a separate, explicit follow-up.
