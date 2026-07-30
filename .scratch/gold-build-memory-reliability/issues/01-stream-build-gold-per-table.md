# Stream build_gold() per table instead of materializing the whole gold layer

Type: task
Status: open

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
