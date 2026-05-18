# Milestone v1.1 - Project Summary

**Generated:** 2026-05-17  
**Workstream:** neo4j-pipe  
**Purpose:** Team onboarding and project review  
**Status:** In progress

---

## 1. Project Overview

EdgarTools Platform delivers structured, business-ready SEC EDGAR data through an AWS-focused ETL platform. The active runtime path is SEC EDGAR API to `edgar-warehouse`, S3 bronze and warehouse storage, Snowflake native S3 pull, dbt gold dynamic tables, and Streamlit dashboards.

Milestone v1.1 focuses on the Neo4j bronze-to-graph pipe. Its goal is to fix the path from already-captured bronze and silver data through MDM relationship derivation into Neo4j so graph sync is complete, idempotent, and independently verifiable.

The milestone is intentionally scoped to the existing AWS path and an isolated `neo4j-pipe` workstream. It must not touch loader-fix artifacts, generated deployment JSON, gold refresh behavior, generic Step Functions observability, or non-AWS deployment paths.

Current milestone state:

- Phase 5 has four plan summaries on disk and all Phase 5 focused tests are reported green in those summaries.
- Phase 5 does not yet have a phase-level `05-VERIFICATION.md` artifact, so the phase should still be treated as awaiting formal verification.
- Phase 6 is planned with one TDD plan, but no summary or verification artifact exists yet.
- Phase 7 is still planned at roadmap level only.

## 2. Architecture And Technical Decisions

- **Decision:** Keep MDM and Neo4j downstream of silver ownership rows.
  - **Why:** Phase 5 context explicitly rejects deriving MDM relationships directly from bronze XML. Bronze XML is parsed into silver ownership tables first, then MDM consumes silver.
  - **Phase:** 5

- **Decision:** Repair the existing `parse-ownership-bronze` command instead of adding a second ownership backfill command.
  - **Why:** The command already exists and is the intended operator surface for parsing already-captured Forms 3/4/5 XML without SEC re-fetch.
  - **Phase:** 5

- **Decision:** Use current silver schema fields `form` and `report_date`, not stale `form_type` and `period_of_report`.
  - **Why:** The actual silver DDL uses `sec_company_filing.form` and `report_date`; the stale query blocked ownership bronze parsing.
  - **Phase:** 5

- **Decision:** Prefer artifact-registry reads through `sec_filing_attachment` and `sec_raw_object`.
  - **Why:** This matches the existing warehouse parse path and lets the repair read exact primary XML objects through `object_storage.read_bytes()`.
  - **Phase:** 5

- **Decision:** Validate `MDM_SILVER_DUCKDB` before opening an MDM database session.
  - **Why:** Missing or invalid source configuration must fail clearly and avoid partial mutation.
  - **Phase:** 5

- **Decision:** Validate required silver tables from fixed allowlists only.
  - **Why:** Required table validation must not interpolate operator-controlled identifiers into SQL.
  - **Phase:** 5

- **Decision:** Fix company loading to use `sec_company_sync_state`.
  - **Why:** `sec_tracked_universe` is stale; current silver uses `sec_company_sync_state`.
  - **Phase:** 5

- **Decision:** Coerce fund `aum_as_of_date` strings back to Python dates in `FundResolver`.
  - **Why:** Survivorship stores winning values as strings, and SQLite rejects string values for SQLAlchemy `Date` columns.
  - **Phase:** 5

- **Decision:** Phase 6 should extend existing relationship tests rather than create a new end-to-end fixture.
  - **Why:** All six derivers already exist in `edgar_warehouse/mdm/pipeline.py`; the gap is coverage, skip counters, structured skip events, and full idempotency.
  - **Phase:** 6 planning

## 3. Phases Delivered

| Phase | Name | Status | One-Liner |
|-------|------|--------|-----------|
| 5 | Source To MDM Load Path | Implementation summaries complete; verification missing | Existing bronze XML can be parsed into silver ownership tables, MDM silver preflight now runs before mutation, and five MDM entity domains are reported idempotent in focused tests. |
| 6 | Relationship Derivation Coverage | Planned | Planned TDD work will cover all six relationship types, add broken-down skip counters, and emit structured skip diagnostics. |
| 7 | Neo4j Sync And Verification | Planned | Roadmap phase for idempotent Neo4j node/edge sync and diagnostic `verify-graph` output. |

## 4. Requirements Coverage

Requirement status from `.planning/workstreams/neo4j-pipe/REQUIREMENTS.md`:

- **PIPE-01:** Complete - operator can use existing local or S3-backed silver DuckDB without re-fetching SEC artifacts.
- **PIPE-02:** Pending in requirements file - Phase 5 summaries report all-domain idempotency tests green, but phase verification has not yet promoted this requirement.
- **PIPE-03:** Pending in requirements file - Phase 5 summaries report preflight-before-session behavior, but phase verification has not yet promoted this requirement.
- **REL-01:** Pending - `IS_INSIDER` relationship derivation coverage belongs to Phase 6.
- **REL-02:** Pending - `HOLDS` and `ISSUED_BY` coverage belongs to Phase 6.
- **REL-03:** Pending - `MANAGES_FUND`, `IS_ENTITY_OF`, and `IS_PERSON_OF` coverage belongs to Phase 6.
- **REL-04:** Pending - all-six-types relationship idempotency belongs to Phase 6.
- **GRAPH-01:** Pending - Neo4j node sync belongs to Phase 7.
- **GRAPH-02:** Pending - bounded relationship sync by type belongs to Phase 7.
- **GRAPH-03:** Pending - graph verification diagnostics belong to Phase 7.
- **GRAPH-04:** Pending - repeat-run graph count stability belongs to Phase 7.
- **ISO-01:** Complete - work stayed scoped to `neo4j-pipe` artifacts and avoided loader-fix surfaces.
- **ISO-02:** Complete - work avoided gold refresh, generic Step Functions observability, and unrelated loader refactors.

Audit note: `.planning/workstreams/neo4j-pipe/v1.1-MILESTONE-AUDIT.md` is older than the completed Phase 5 summaries. It still reports `gaps_found` based on local silver candidates with zero ownership rows. The audit should be rerun after formal Phase 5 verification.

## 5. Key Decisions Log

| ID | Decision | Phase | Rationale |
|----|----------|-------|-----------|
| D-01 | Use the existing edgartools-backed ownership parser path for Forms 3/4/5 XML. | 5 | Preserve parser contract and avoid introducing a custom parser. |
| D-02 | Repair silver ownership tables first. | 5 | MDM and Neo4j depend on silver ownership rows. |
| D-03 | Do not derive MDM relationships directly from bronze XML. | 5 | Keeps the pipeline layered: bronze to silver to MDM to Neo4j. |
| D-04 | Keep work in the `neo4j-pipe` worktree and workstream. | 5 | Prevents conflict with the active loader-fix workstream. |
| D-05 | Do not edit generated deployment JSON, gold/dbt, or unrelated loader code. | 5 | Maintains AWS path isolation and avoids concurrent edit overlap. |
| D-06 | Repair `parse-ownership-bronze` rather than adding another command. | 5 | Keeps the operator surface simple and existing. |
| D-07 | Use `form` and `report_date` in `sec_company_filing`. | 5 | Matches current silver DDL. |
| D-08 | Prefer registry reads via `sec_filing_attachment` and `sec_raw_object`. | 5 | Reads the exact already-captured primary artifacts. |
| D-09 | Treat bronze primary XML as a prerequisite. | 5 | Missing artifacts are reported, not silently re-fetched. |
| D-10 | Keep SEC fetch/artifact capture repair out of the default Phase 5 path. | 5 | Avoids loader-workstream overlap. |
| D-11 | Add preflight validation for `mdm run`, `mdm derive-relationships`, and `mdm load-relationships`. | 5 | Missing source config must fail before mutation. |
| D-12 | Require nonzero company, filing, and ownership rows before company-person graph validation. | 5 | Prevents false-positive Neo4j readiness. |
| D-02-P6 | Add broken-down relationship skip counters. | 6 planning | Operators need coverage diagnostics, not only aggregate skipped counts. |
| D-03-P6 | Emit structured skip JSON lines for silver-derived relationship skips. | 6 planning | Operators can cross-reference skipped CIKs/accessions. |
| D-04-P6 | Test all six relationship types for idempotency in one pass. | 6 planning | Directly satisfies REL-04. |

## 6. Tech Debt And Deferred Items

- Phase 5 still needs formal phase verification. The summaries report green focused tests, but there is no `05-VERIFICATION.md`.
- The requirements file has not fully caught up with the Phase 5 summaries: PIPE-02 and PIPE-03 remain pending even though the summaries claim implementation success.
- The milestone audit is stale relative to Phase 5 execution and should be rerun after verification.
- Survivorship currently stores staged field values as strings. `FundResolver` now handles `aum_as_of_date`, but broader typed survivorship remains deferred.
- Full AWS 100-company proof is deferred until credentials and Neo4j environment are available.
- Phase 6 intentionally defers end-to-end real DuckDB relationship tests; it starts with the existing in-memory SQLite relationship fixture.
- Phase 7 owns Neo4j sync, edge verification, pending-row diagnostics, and live smoke documentation.

## 7. Getting Started

- **Run dependency-managed Python commands with uv:** `uv run pytest tests/unit tests/architecture`
- **Run focused Phase 5 tests:** `uv run --extra mdm-runtime --extra s3 --with pytest pytest tests/mdm/test_source_to_mdm_load_path.py tests/application/test_parse_ownership_bronze.py -q`
- **Read the Phase 5 operator runbook:** `docs/aws-mdm-source-to-mdm.md`
- **Main CLI entry point:** `edgar_warehouse/cli.py`
- **Warehouse command dispatch:** `edgar_warehouse/application/warehouse_orchestrator.py`
- **MDM command preflight:** `edgar_warehouse/mdm/cli.py`
- **MDM pipeline and relationship derivation:** `edgar_warehouse/mdm/pipeline.py`
- **Ownership parser adapter:** `edgar_warehouse/parsers/ownership.py`
- **Phase planning artifacts:** `.planning/workstreams/neo4j-pipe/phases/`
- **Current milestone roadmap:** `.planning/workstreams/neo4j-pipe/ROADMAP.md`

Suggested next local workflow:

1. Run `$gsd-verify-phase 05` for formal Phase 5 verification.
2. Update or rerun the milestone audit so requirements coverage reflects Phase 5 work.
3. Execute Phase 6 plan `06-01-PLAN.md`.
4. Plan Phase 7 once relationship derivation coverage is verified.

---

## Stats

- **Timeline:** 2026-05-16 to 2026-05-17
- **Phases:** 0 formally verified / 3 total
- **Implementation summaries:** 4 Phase 5 plan summaries
- **Planned phases:** Phase 6 has 1 plan; Phase 7 is still TBD
- **Commits since 2026-05-16:** 53
- **Recent milestone diff sample:** 12 files changed, 2349 insertions, 43 deletions across the latest 8 commits inspected
- **Contributors in range:** Aneena Ananth, Paul Ananth

## Source Artifacts Read

- `.planning/workstreams/neo4j-pipe/ROADMAP.md`
- `.planning/workstreams/neo4j-pipe/REQUIREMENTS.md`
- `.planning/workstreams/neo4j-pipe/STATE.md`
- `.planning/workstreams/neo4j-pipe/v1.1-MILESTONE-AUDIT.md`
- `.planning/workstreams/neo4j-pipe/phases/05-source-to-mdm-load-path/05-CONTEXT.md`
- `.planning/workstreams/neo4j-pipe/phases/05-source-to-mdm-load-path/05-RESEARCH.md`
- `.planning/workstreams/neo4j-pipe/phases/05-source-to-mdm-load-path/05-01-SUMMARY.md`
- `.planning/workstreams/neo4j-pipe/phases/05-source-to-mdm-load-path/05-02-SUMMARY.md`
- `.planning/workstreams/neo4j-pipe/phases/05-source-to-mdm-load-path/05-03-SUMMARY.md`
- `.planning/workstreams/neo4j-pipe/phases/05-source-to-mdm-load-path/05-04-SUMMARY.md`
- `.planning/workstreams/neo4j-pipe/phases/06-relationship-derivation-coverage/06-CONTEXT.md`
- `.planning/workstreams/neo4j-pipe/phases/06-relationship-derivation-coverage/06-RESEARCH.md`
- `.planning/workstreams/neo4j-pipe/phases/06-relationship-derivation-coverage/06-01-PLAN.md`
- `.planning/PROJECT.md`
