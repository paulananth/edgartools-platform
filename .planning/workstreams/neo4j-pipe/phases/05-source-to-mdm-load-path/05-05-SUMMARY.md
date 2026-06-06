---
plan: "05-05"
phase: 05-source-to-mdm-load-path
status: complete
completed_at: "2026-06-06"
---

# Plan 05-05 Summary: Live Phase 5 Closeout

## What Was Done

1. Revalidated the bounded real-data Phase 5 sample:
   - ownership issuer CIK 712515 / accession 0000712515-26-000049
   - ADV adviser/fund sample CRD/CIK 105958 / accession ADV-105958-20241218
   - local Postgres DB `mdm_phase5_filtered_20260605205244`
   - filtered silver DuckDB `/tmp/gsd_phase5_filtered_silver.duckdb`

2. Confirmed local MDM load and coverage:
   - `mdm_company`, `mdm_person`, `mdm_security`, `mdm_adviser`, `mdm_fund` are each 1
   - `mdm_relationship_instance` is 4
   - `mdm coverage-report` shows 0 gap for all five domains

3. Fixed two live Snowflake graph-sync defects found during the retry:
   - `SnowflakeGraphSyncExecutor.sync` now executes generated SQL one statement at a time, matching Snowflake Connector single-statement behavior.
   - `render_graph_tables` now creates all 11 relationship-specific `GRAPH_EDGE_*` views, including `AUDITED_BY`, `EMPLOYED_BY`, and `INSTITUTIONAL_HOLDS`.

4. Populated the dev Snowflake MDM mirror for the bounded sample:
   - target: `EDGARTOOLS_DEV.MDM`
   - rows loaded: 15 entities, 11 relationship types, 4 active relationship instances, and all five domain tables.

5. Ran live Snowflake graph sync:
   - command: `edgar-warehouse mdm sync-graph --target-database EDGARTOOLS_DEV --target-schema NEO4J_GRAPH_MIGRATION --mdm-database EDGARTOOLS_DEV --mdm-schema MDM`
   - result: `graph_nodes_synced=15`, `graph_edges_synced=4`, target schema `NEO4J_GRAPH_MIGRATION`

6. Verified the Phase 5 parity gate:
   - all 11 relationship-specific `GRAPH_EDGE_*` views exist
   - `IS_INSIDER`, `HOLDS`, `ISSUED_BY`, and `MANAGES_FUND` each have 1 graph edge
   - `MDM_MINUS_GRAPH = 0` for every active relationship type
   - missing graph edge endpoint rows = 0

## Verification

```bash
uv run --extra mdm-runtime --extra s3 --with pytest pytest tests/mdm/test_source_to_mdm_load_path.py -k coverage_report -q
# 1 passed, 18 deselected

MDM_DATABASE_URL=sqlite:// uv run edgar-warehouse mdm coverage-report --help
# exit 0

uv run --extra mdm-runtime --extra s3 --with pytest pytest tests/mdm/test_source_to_mdm_load_path.py tests/application/test_parse_ownership_bronze.py -q
# 32 passed, 3 warnings

uv run --extra mdm-runtime --extra snowflake --with pytest pytest tests/mdm/test_snowflake_graph_migration.py tests/mdm/test_cli_snowflake_graph.py -q
# 12 passed
```

## Requirements Satisfied

- PIPE-04: `mdm coverage-report` exists, exits 0 with gaps, and reports 0 gap for the complete real-data sample.
- PIPE-05: Snowflake graph sync materializes the MDM mirror into `NEO4J_GRAPH_MIGRATION`; parity holds with `MDM_MINUS_GRAPH = 0`.
- D-17/D-18: graph sync uses SnowflakeGraphSyncExecutor/Snowflake tables, not a Bolt/Neo4j endpoint.
- D-30: Phase 5 validation evidence is recorded in `05-VALIDATION.md`.

## Notes

- The live source did not contain one CIK with both ownership and ADV rows. The closeout uses a bounded real-data two-source sample and records that deviation explicitly in validation.
