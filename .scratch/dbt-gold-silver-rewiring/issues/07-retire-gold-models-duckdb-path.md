# 07 — Retire gold_models.py and Delete the DuckDB Gold-Build Path

**What to build:** Once every gold table has a working non-DuckDB path
(Tickets 02-06 all complete), delete `edgar_warehouse/serving/gold_models.py`'s
DuckDB-reading `_build_*` functions, `_gold_table_builders()`,
`iter_gold_tables()`, and `build_gold()`, and convert
`validate_data_quality.py` (the real remaining caller of `build_gold()`) to
validate against live Snowflake gold tables directly instead of materializing
the Python dict from a local DuckDB file. Checked directly: there are exactly
two real callers of these functions today —
`application/warehouse_orchestrator.py` (the production write path, streams
`iter_gold_tables()`, already made unnecessary by Tickets 02-06) and
`application/commands/validate_data_quality.py`. Two other files
(`edgar_warehouse/gold.py` and
`application/workflows/serving_publish.py`) re-export `build_gold` but have
zero importers anywhere in the repo — dead re-export shims, not real
consumers; delete them here rather than leaving them as stale imports of a
function that no longer exists.

**Blocked by:** 02, 03, 04, 05, 06

**Status:** ready-for-agent

- [ ] `gold_models.py`'s DuckDB-reading builder functions are deleted
- [ ] `validate_data_quality.py` no longer calls `build_gold()` /
      `iter_gold_tables()`; it validates against live Snowflake gold tables
      instead
- [ ] The dead `build_gold` re-export shims in `edgar_warehouse/gold.py` and
      `application/workflows/serving_publish.py` are deleted (confirm no
      importer exists before deleting, since this check is time-sensitive)
- [ ] No remaining `import duckdb` reference tied to gold-building anywhere
      under `edgar_warehouse/serving/`
- [ ] Full test suite green
