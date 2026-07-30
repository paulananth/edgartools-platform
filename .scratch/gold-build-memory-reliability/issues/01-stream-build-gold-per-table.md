# Stream build_gold() per table instead of materializing the whole gold layer

Type: task
Status: resolved

## Question

`build_gold()` (`edgar_warehouse/serving/gold_models.py:1224`) returns a fully-realized
`dict[str, pa.Table]` — every table is built eagerly as the dict literal executes, so by the
time the largest table (`sec_thirteenf_holding`, ~6.8M rows) starts building, all ~24 prior
tables (`dim_company` through `fact_adv_private_fund`) are still alive in memory. The caller
(`warehouse_orchestrator.py:476-528`) then makes two more full passes over the same dict —
`write_gold_to_storage_manifest` and `write_gold_to_serving_export` — before `del gold_tables`
frees anything. Peak memory is the sum of every gold table simultaneously, not the largest one.

This reproduced live on 2026-07-30: `daily_incremental`'s Fargate task (4096MB) OOM-killed
(exit 137) three times in a row, identically, mid-`sec_thirteenf_holding`, exhausting
`MaxAttempts:3` and failing the execution.

Implement the fix recommended by this session's `/gof-refactor-reviewer` pass: turn
`build_gold` into a generator of `(name, table)` pairs; change the caller to stream — build one
table, write it to storage, export it to Snowflake, discard it, move to the next — instead of
three full passes over the whole gold layer held in memory at once. Use a plain Python
generator, not a formal `Iterator` class (per the review: Iterator is "largely subsumed by
modern language features").

Concretely:
1. Add characterization tests around current `build_gold()` output (table names, schemas, row
   counts) if not already adequately covered, so the refactor has a regression safety net.
2. Convert `build_gold` to `yield name, table` instead of building the dict inline.
3. Change the caller at `warehouse_orchestrator.py:476` to iterate once per table: build →
   write storage → export → `del table` → next.
4. Re-verify `gold_manifest_entries`/`snowflake_export_counts` aggregation still matches
   today's all-at-once semantics (both are currently built as lists/dicts over the full
   iteration — should still work over a generator, but confirm).
5. Confirm peak memory drops materially — ideally re-run the exact failing scenario (or a
   scaled-down equivalent) to prove the fix before considering this resolved.

Follow this repo's standard `/implement` flow: TDD at the seams above, typecheck/test
regularly, `/code-review` before commit.

## Answer

Implemented on branch `claude/gold-build-streaming` (not yet merged/deployed).

1. **Characterization tests**: `tests/unit/test_gold_models_streaming.py` — a real,
   schema-backed `SilverDatabase` fixture (not a hand-rolled stub, per this repo's
   INSTITUTIONAL_HOLDS/EMPLOYED_BY 5-whys lesson), pinned against a hardcoded expected
   table-name set (guards against a silently dropped/renamed builder), plus a non-empty-row
   equivalence check between `build_gold()` and `iter_gold_tables()`, plus a laziness test
   proving `sec_thirteenf_holding` (the table that actually OOM'd) isn't built until the
   generator reaches it.
2. `build_gold()` (`gold_models.py`) split into `_gold_table_builders()` (the registry) +
   `iter_gold_tables()` (a plain generator yielding `(name, table)` one at a time).
   `build_gold()` itself is kept as `dict(iter_gold_tables(db))` — it still has one real
   production caller, `validate_data_quality.py`, that needs random access across the whole
   gold layer and is out of scope here (see map's "Not yet specified").
3. `warehouse_orchestrator.py`'s `GOLD_AFFECTING_COMMANDS` caller now streams: build one
   table → write it to storage → export it to Snowflake → `del table` → next. New per-table
   helpers `write_gold_table_manifest_entry()` (`gold_models.py`) and
   `write_gold_table_to_serving_export()` (`serving/targets/snowflake.py`, alongside hoisting
   the export map to a module-level `GOLD_EXPORT_MAP` constant) back the loop; the old
   whole-dict `write_gold_to_storage_manifest`/`write_gold_to_serving_export` are kept as thin
   wrappers over the per-table helpers for callers that still want the batch form.
4. Aggregation verified equivalent in content. One deliberate **behavior change** beyond the
   ticket's literal ask: `db.record_gold_manifest` is now called once per table, inside the
   loop, instead of once at the end with the full list — confirmed safe because it's an
   idempotent `ON CONFLICT (run_id, storage_layer, table_name)` upsert. This means a later
   table's export failure can no longer erase the fact that earlier tables' manifests were
   already durably recorded (a regression the initial streaming pass introduced and a review
   caught before commit). Pipeline telemetry was also simplified: the old three separate
   `gold_storage_write_completed`/`gold_snowflake_export_completed` phase-timing events no
   longer represent distinct phases once build/write/export are fused per table, so they were
   folded into a single `gold_build_completed` event carrying the combined duration plus all
   the same row-count/manifest/export-count data. `gold_publish_completed`'s payload shape
   (`duration_seconds`, `gold_row_counts`, `snowflake_export_counts`) is unchanged — it's the
   only event an external consumer (`scripts/ops/verify-counts.py`) reads.
5. **Not done, deliberately** — no prod re-run has confirmed peak memory actually drops.
   Reasoned (not measured) from CloudWatch's `gold_table_completed` row counts across all 4
   failed attempts: by the time `sec_thirteenf_holding` (~6.8M rows) started, ~7M rows across
   15 predecessor tables were still alive in the old eager-dict shape — streaming removes that
   predecessor-table pressure, which is real, but does not by itself guarantee one 6.8M-row
   table's own DuckDB-materialization + Arrow + double-buffered-parquet-serialization footprint
   fits in 4096MB. Ticket 03 (the tactical memory-ceiling bump) is the ticket expected to
   actually close this out empirically, via its own planned redeploy + fresh
   `daily_incremental` execution. Recorded in CLAUDE.md's new "Gold-build memory /
   daily_incremental OOM 5-whys" section as "fixed, not yet deployed."

Verification: `uv run python -m pytest tests/unit tests/architecture -q` — 824 passed, 4
skipped (pre-existing skips, unrelated). `mypy` on the three touched modules shows no new
errors introduced by this change (pre-existing unrelated errors in
`warehouse_orchestrator.py` remain, out of scope). Reviewed via `/code-review` (Standards +
Spec sub-agents in parallel) before commit; both findings that survived review (CLAUDE.md
5-whys documentation gap, misleading duplicate-duration telemetry) were fixed, and the
`record_gold_manifest` timing issue above was caught by a subsequent advisor pass and fixed
before commit.

Not yet merged to `main` or deployed — next step is opening a PR (per this repo's history of
routing real code changes through PRs, unlike the docs-only tickets which went straight to
`main`).
