# Phase 8: Neo4j Native App Verification Gaps - Context

**Gathered:** 2026-07-12
**Status:** Ready for planning
**Source:** Phase 7 `07-00` live NO-GO preflight and user request to resolve compatibility gaps

## Phase Boundary

Resolve repository compatibility with the installed Neo4j Graph Analytics for Snowflake API,
separate Native App readiness/capability failures from MDM↔graph parity failures, and produce dated
live evidence for GRAPH_INFO, BFS, and LIST_GRAPHS. Do not modify Phase 6 parsers, loads, or active
relationship dispositions.

## Locked Decisions

- Use only the Snowflake-hosted Neo4j Native App; do not restore Aura/Bolt.
- Use `SNOW_CONNECTION=snowconn` for all dev DDL and live verification.
- Current algorithm calls use `(compute_pool_selector VARCHAR, configuration OBJECT)` with
  `project`, `compute`, and `write` sections and camelCase keys.
- SQL success does not mean Native App job success; `JOB_STATUS=ERROR` is a failed capability.
- Verification output must separately report `parity`, `readiness`, and `capability` domains.
- Missing compute pool/app/grants are readiness failures. Missing/extra identities or properties
  are parity failures. Algorithm/procedure job errors are capability failures.
- GRAPH_INFO and BFS must be updated to the current documented API and tested live.
- LIST_GRAPHS must use its installed `EXPERIMENTAL.LIST_GRAPHS()` location. If its app-internal
  `LIST_FILES` child-job failure persists, record it as an external blocker with exact app version,
  command, date, and error; do not patch Marketplace application internals.
- Phase 8 completion may document a confirmed external Native App blocker, as allowed by GVER-02.
- Phase 7's stricter RPRE-01 gate is not silently weakened in Phase 8; any architecture revision
  removing LIST_GRAPHS from that gate requires an explicit user decision after Phase 8 evidence.

## Canonical References

- `.planning/workstreams/fix-pipelines/phases/07-source-coverage-exclusions-and-artifact-hygiene/07-NATIVE-APP-PREFLIGHT.md`
- `edgar_warehouse/mdm/snowflake_graph.py`
- `tests/mdm/test_snowflake_graph_migration.py`
- `tests/mdm/test_cli_snowflake_graph.py`
- `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql`
- Neo4j Graph Analytics for Snowflake current BFS and operations documentation.

## Deferred

- Phase 7 temporal generation schema implementation.
- Changes to Neo4j Marketplace application internals.
- General dashboard redesign.

