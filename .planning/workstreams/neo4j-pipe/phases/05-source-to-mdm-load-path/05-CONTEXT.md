# Phase 5: Source To MDM Load Path - Context

**Gathered:** 2026-06-02 (updated from 2026-05-16 assumptions mode)
**Status:** Ready for planning (05-05 plan)

<domain>
## Phase Boundary

Phase 5 proves that existing bronze/silver data can flow through the complete
pipe — parse-ownership-bronze → MDM entities → MDM relationships → Snowflake
graph tables — without re-fetching SEC artifacts and without touching the
parallel loader-fix workstream.

Plans 05-01 through 05-04 (executed 2026-05-16 to 2026-05-17) fixed the
schema mismatch in parse-ownership-bronze, added MDM silver preflight, fixed
FundResolver date coercion, and proved entity-load idempotency. Tests pass
(28/28). Plan 05-05 adds the live E2E validation, entity coverage audit and
gate, loader fixes for any gaps found, and tracking close-out that officially
marks Phase 5 complete.

Phase 5 is complete when:
1. All 28 existing tests pass.
2. `mdm coverage-report` shows 0 gap (ownership-sourced entities — see D-28 for security scope).
3. A live single-CIK full E2E run succeeds: S3 bronze → silver → MDM entities
   → MDM relationships → Snowflake NEO4J_GRAPH_MIGRATION graph tables, with all
   11 GRAPH_EDGE_* tables having at least 1 row.
4. ROADMAP.md, REQUIREMENTS.md, VALIDATION.md, workstream STATE.md, and global
   .planning/STATE.md are updated.
</domain>

<decisions>
## Implementation Decisions

### Carried Forward: Bronze-To-Silver Ownership Backfill (Plans 05-01–05-04)
- **D-01:** Use the existing edgartools-backed ownership parser path to populate
  missing Forms 3/4/5 silver tables from bronze primary XML artifacts.
- **D-02:** The repair target is silver ownership data: `sec_ownership_reporting_owner`,
  `sec_ownership_non_derivative_txn`, and `sec_ownership_derivative_txn`.
- **D-03:** Do not derive MDM relationships directly from bronze XML. MDM and Neo4j
  must remain downstream of silver ownership rows.

### Carried Forward: Workstream Isolation
- **D-04:** Keep all Phase 5 implementation in the `workspace/neo4j-pipe` worktree
  and the `neo4j-pipe` planning workstream.
- **D-05:** Do not edit loader-fix artifacts, generated deployment JSON, gold/dbt
  assets, Step Functions observability work, or unrelated loader code.

### Carried Forward: Command Repair (Done in 05-02)
- **D-06:** Repaired and use the existing `parse-ownership-bronze` command (not a new command).
- **D-07:** Fixed silver schema mismatch: `sec_company_filing` uses `form` and `report_date`,
  not `form_type` and `period_of_report`.
- **D-08:** Prefer artifact-registry reads (`sec_filing_attachment` + `sec_raw_object`) where
  possible. Path-based bronze lookup valid only when registry rows are unavailable.

### Carried Forward: Bronze Artifact Prerequisite
- **D-09:** Treat already-captured bronze primary XML as the prerequisite. If XML artifacts
  are absent, report the gap clearly — do not silently re-fetch SEC data.
- **D-10:** Any SEC fetch or artifact capture repair is outside Phase 5. Phase 5 uses only
  existing S3 bronze. The researcher must select a test CIK that already has bronze
  Forms 3/4/5 + ADV filings in S3.

### Carried Forward: MDM Source Validation (Done in 05-03)
- **D-11:** Shared `_require_silver_reader()` preflight runs before any MDM mutation
  (`mdm run`, `mdm derive-relationships`, `mdm load-relationships`).
- **D-12:** Company-person relationship readiness requires nonzero `sec_company`,
  `sec_company_filing`, and `sec_ownership_reporting_owner` rows before MDM person
  and `IS_INSIDER` derivation.

### Live E2E Validation (Plan 05-05)
- **D-13:** Phase 5 requires a live S3 run before close-out — local test coverage alone
  is insufficient. The live run is encoded in a 5th plan (05-05-PLAN.md).
- **D-14:** Researcher selects the test CIK based on available S3 bronze — must be a
  company that has both Forms 3/4/5 bronze and ADV filing bronze already in S3 so
  all entity types and relationship types can be exercised.
- **D-15:** Success criterion for the live run: full silver-to-MDM-to-Snowflake round
  trip succeeds for the selected CIK. Specifically: `parse-ownership-bronze` writes
  silver rows, `mdm run` loads all 5 entity types, `mdm derive-relationships` creates
  MDM relationship rows, `mdm sync-graph` materializes to Snowflake NEO4J_GRAPH_MIGRATION
  with all 11 GRAPH_EDGE_* tables having at least 1 row.
- **D-16:** MDM target for the 05-05 live run: local Postgres via Colima + Docker
  (`docker run --platform linux/amd64 postgres:15`). Local Postgres avoids VPC
  dependency and is more production-realistic than SQLite.
- **D-17:** Snowflake sync uses `SNOWFLAKE_*` env vars or SnowCLI connection
  `edgartools-dev` (available locally on the workstation). `mdm sync-graph` targets
  Snowflake NEO4J_GRAPH_MIGRATION schema via `SnowflakeGraphSyncExecutor` —
  NOT a bolt:// Neo4j endpoint.
- **D-18:** `neo4j-pipe` (MDM → Snowflake graph table export) and `neo4j-snowflake`
  (Snowflake Native App for graph analytics) are parallel workstreams. Phase 5's
  05-05 proves only that MDM data lands in Snowflake graph tables. Whether the
  Neo4j Snowflake app correctly reads those tables is neo4j-snowflake Phase 3 scope.

### Entity Coverage (Part of 05-05)
- **D-19:** New `mdm coverage-report` subcommand: reads silver DuckDB + MDM, computes
  silver_count vs mdm_count per domain, reports gap and exclusion reason per domain.
  Exits 0 even when gaps are found (reporting tool, not a hard gate command).
- **D-20:** `mdm coverage-report` is a Phase 5 close-out gate: Phase 5 is not done
  until coverage-report shows 0 gap (within the Phase 5 coverage scope below).
- **D-21:** Coverage scope and exclusion policy per domain:
  - **Companies:** Only `tracking_status = 'active'` companies. Inactive/dropped are
    intentionally excluded and coverage-report must label them as such.
  - **Persons:** Non-corporate reporting owners (`is_company = false` or equivalent).
    Corporate owners are intentionally excluded.
  - **Securities (Phase 5 scope):** Ownership-sourced only — from
    `sec_ownership_non_derivative_txn` + `sec_ownership_derivative_txn`. XBRL-sourced
    securities (from `sec_financial_fact`) are Phase 6 scope (see D-28).
  - **Advisers:** All adviser rows in silver that correspond to active tracked CIKs.
  - **Funds:** All private funds in `sec_private_fund` — zero acceptable exclusions.
- **D-22:** Coverage-report CI tests: assert zero gap against a complete DuckDB fixture
  (1 company, 1 adviser, 1 person, 1 security, 1 fund in both silver AND MDM).
  Tests go in `tests/mdm/test_source_to_mdm_load_path.py` alongside existing Phase 5 tests.
- **D-23:** If the 05-05 live run or coverage-report finds loader gaps (silver rows
  silently dropped without MDM entity): fix the loader in the same 05-05 plan.
- **D-24:** XBRL security loader: researcher investigates `sec_financial_fact` schema to
  determine how to identify a unique security entity from XBRL companyfacts. If the
  mapping is underdefined, XBRL securities are deferred to Phase 6 with coverage-report
  noting the exclusion reason.

### Phase 5 → Phase 6 Handoff
- **D-25:** Phase 5 sign-off gate: full 5-domain round-trip against real S3 bronze
  (not mock/fixture data).
- **D-26:** Phase 6 planning starts AFTER Phase 5 is merged to main. Do not plan Phase 6
  while Phase 5 PR is still open.
- **D-27:** Phases 6 and 7 are merged into one new phase: **"Full Graph Coverage And
  Verification"** (new Phase 6). The original Phase 7 entry is deleted from ROADMAP.md.
- **D-28:** XBRL-sourced securities (from `sec_financial_fact`) are Phase 6 scope,
  not Phase 5. Researcher maps `sec_financial_fact` → MDM security entity before Phase 6 planning.
- **D-29:** New Phase 6 success criteria:
  - All 11 GRAPH_EDGE_* types in `snowflake_graph.py` have rows for all active tracked CIKs.
  - Full tracking universe (all active CIKs) successfully flows: silver → MDM entities →
    MDM relationships → Snowflake graph tables.
  - Zero-delta idempotency: second full pipeline run adds exactly 0 new rows.
  - `mdm verify-graph` reports Snowflake graph table row counts per entity + edge type.
  - `mdm sync-graph` supports bounded sync by relationship type + per-type limit (GRAPH-02).

### Tracking Close-out (Part of 05-05)
- **D-30:** 05-05 plan is responsible for all tracking close-out after live validation passes:
  - ROADMAP.md: mark 05-03, 05-04, 05-05 complete; rewrite Phase 6 entry (absorb Phase 7
    scope); delete Phase 7 entry.
  - REQUIREMENTS.md: mark PIPE-02 and PIPE-03 complete; add PIPE-04 (mdm coverage-report
    0-gap gate) and PIPE-05 (full E2E live round-trip with Snowflake graph sync).
  - VALIDATION.md: set `nyquist_compliant: true` (sign-off condition: 28 tests pass +
    live E2E output committed + coverage-report 0 gap).
  - Workstream STATE.md: update to Phase 5 complete, Phase 6 ready to plan.
  - Global `.planning/STATE.md`: update v1.1 neo4j-pipe milestone to show Phase 5 at 100%,
    Phase 6 (Full Graph Coverage And Verification) ready to plan.

### Claude's Discretion
- Bounded `--limit` / `--cik-list` / `--accession-list` execution controls for the live
  run are at agent discretion — add only if needed for safe bounded validation.
- Researcher determines which specific CIK (from available S3 bronze) best exercises all
  entity types and all 11 edge types in a single run.
- Researcher determines the precise MDM entity exclusion thresholds (e.g., the exact
  SQL predicate for `is_company` in `sec_ownership_reporting_owner`) if not already
  explicit in the codebase.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Workstream Planning
- `.planning/workstreams/neo4j-pipe/ROADMAP.md` — Phase 5/6/7 definitions, success criteria, and plan tracking
- `.planning/workstreams/neo4j-pipe/REQUIREMENTS.md` — PIPE-01–PIPE-05, REL-01–REL-04, GRAPH-01–GRAPH-04
- `.planning/workstreams/neo4j-pipe/v1.1-MILESTONE-AUDIT.md` — milestone-level context

### Silver → MDM Load Path
- `edgar_warehouse/cli.py` — parse-ownership-bronze CLI entry point; `--limit` and `--accession-list` args
- `edgar_warehouse/application/warehouse_orchestrator.py` — `_run_parse_ownership_bronze()` dispatch; artifact-registry read path
- `edgar_warehouse/parsers/ownership.py` — edgartools `Ownership.from_xml()` adapter
- `edgar_warehouse/silver_store.py` — merge methods and schemas for ownership reporting owners and transactions

### MDM Pipeline
- `edgar_warehouse/mdm/cli.py` — `_require_silver_reader()`, `_handle_sync_graph()`, `_handle_derive_relationships()`, `mdm coverage-report` to be added here
- `edgar_warehouse/mdm/pipeline.py` — `run_companies()`, `run_advisers()`, `run_persons()`, `run_securities()`, `run_funds()`; `sec_company_sync_state` fix
- `edgar_warehouse/mdm/snowflake_graph.py` — `SnowflakeGraphSyncExecutor`, `SnowflakeGraphSyncConfig`, all 11 GRAPH_EDGE_* and 7 GRAPH_NODE_* table names, `ALLOWED_RELATIONSHIP_TYPES`

### Tests
- `tests/mdm/test_source_to_mdm_load_path.py` — Phase 5 MDM tests (28 passing); coverage-report CI tests to be added here
- `tests/application/test_parse_ownership_bronze.py` — Phase 5 parse-ownership-bronze tests

### Ops Reference
- `docs/aws-mdm-source-to-mdm.md` — operator runbook created in 05-04; update with live run instructions in 05-05
- `scripts/ops/check-neo4j-e2e.py` — established pattern for ops diagnostic scripts

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SnowflakeGraphSyncExecutor.from_env()` in `edgar_warehouse/mdm/snowflake_graph.py` — already
  reads env vars for Snowflake connectivity; `mdm sync-graph` already dispatches to it.
- `_require_silver_reader()` in `edgar_warehouse/mdm/cli.py:420` — shared preflight; all MDM
  mutation handlers already call it.
- `_ENTITY_TYPE_REQUIRED_TABLES` and `_REQUIRED_TABLES_RELATIONSHIP_READINESS` in `mdm/cli.py` —
  existing allowlists; coverage-report can reference these.
- DuckDB fixture pattern from 05-01 — coverage-report CI tests reuse the same real-DuckDB fixture
  approach with all 5 entity domains.

### Established Patterns
- MDM commands hydrate remote silver into local DuckDB, mutate locally, publish back when root is remote.
- Bronze filing artifacts registered through `sec_raw_object` + `sec_filing_attachment`; artifact-registry
  read is the canonical path.
- MDM upsert via SQLAlchemy survivorship — the merge strategy determines idempotency behavior.
- `SnowflakeGraphSyncExecutor` materializes MDM tables into Snowflake `NEO4J_GRAPH_MIGRATION` schema,
  not a bolt:// Neo4j endpoint.

### Integration Points
- `mdm coverage-report`: new `argparse` subcommand in `edgar_warehouse/mdm/cli.py`; reads both
  `MDM_SILVER_DUCKDB` (silver) and `EDGAR_MDM_DATABASE_URL` (MDM Postgres) to compute deltas.
- `mdm sync-graph` already routes through `SnowflakeGraphSyncExecutor`; 05-05 verifies it works
  against the dev Snowflake account with the test CIK's data.
- Colima + `postgres:15` container: set `EDGAR_MDM_DATABASE_URL=postgresql://...@localhost:5432/mdm`
  for the 05-05 live run.
- `sec_ownership_reporting_owner.is_company` (or equivalent field) is the predicate that distinguishes
  natural persons from corporate owners in person-domain coverage.
</code_context>

<specifics>
## Specific Ideas

- `mdm coverage-report` output format should be a table: `domain | silver_count | mdm_count | gap | reason`
  where `reason` explains exclusions (e.g., "corporate owners excluded", "tracking_status != active").
- The 05-05 live run CIK must have both Forms 3/4/5 bronze AND ADV filing bronze already in S3
  (D-10 holds — no SEC fetching). Researcher checks S3 availability before selecting.
- VALIDATION.md sign-off: `nyquist_compliant: true` requires all three conditions met and committed.
- Phase 5 close-out commits Phase 6 ROADMAP.md rewrite in the same PR as the 05-05 plan — so that
  Phase 6 planning can begin immediately after merge.
- `mdm sync-graph` success check: inspect Snowflake `NEO4J_GRAPH_MIGRATION` schema after sync;
  all 11 `GRAPH_EDGE_*` tables must have at least 1 row for the test CIK.
</specifics>

<deferred>
## Deferred Ideas

- **XBRL-sourced securities (Phase 6):** `sec_financial_fact` → MDM security entity mapping.
  Researcher investigates `sec_financial_fact` schema before Phase 6 planning. If underdefined,
  Phase 5 coverage-report notes the exclusion reason; Phase 6 defines and implements the mapping.
- **Full 100-company AWS runtime proof:** Full production tracking universe remains a Phase 6
  success criterion, not Phase 5.
- **neo4j-snowflake Native App verification:** Whether the Snowflake-hosted Neo4j graph analytics
  app correctly reads the NEO4J_GRAPH_MIGRATION tables produced by `mdm sync-graph` is
  neo4j-snowflake Phase 3 scope — parallel workstream, not neo4j-pipe Phase 5.
- **SEC artifact re-fetch or missing-bronze capture repair:** Deferred unless explicitly requested.
  Phase 5 uses only existing S3 bronze (D-09/D-10).
</deferred>

---

*Phase: 05-source-to-mdm-load-path*
*Context gathered: 2026-06-02*
