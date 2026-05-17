# Phase 5: Source To MDM Load Path - Discussion Log (Assumptions Mode)

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md -- this log preserves the analysis.

**Date:** 2026-05-16
**Phase:** 05-Source To MDM Load Path
**Mode:** assumptions
**Areas analyzed:** Bronze-to-silver ownership backfill, independent workstream isolation, existing command repair, bronze artifact prerequisite, MDM source validation

## Assumptions Presented

### Bronze-To-Silver Ownership Backfill

| Assumption | Confidence | Evidence |
|------------|------------|----------|
| Use edgartools-backed parsing to populate missing Forms 3/4/5 silver ownership tables before MDM/Neo4j derivation. | Confident | `edgar_warehouse/parsers/ownership.py`, `edgar_warehouse/mdm/pipeline.py`, `.planning/workstreams/neo4j-pipe/v1.1-MILESTONE-AUDIT.md` |
| Keep MDM relationships downstream of silver rows instead of parsing relationship edges directly from bronze XML. | Confident | `edgar_warehouse/mdm/pipeline.py`, `tests/mdm/test_pipeline_relationships.py`, `.planning/workstreams/neo4j-pipe/ROADMAP.md` |

### Independent Workstream Isolation

| Assumption | Confidence | Evidence |
|------------|------------|----------|
| All work stays in `workspace/neo4j-pipe` and avoids loader-fix artifacts. | Confident | `.planning/PROJECT.md`, `.planning/workstreams/neo4j-pipe/REQUIREMENTS.md`, `.planning/COORDINATION.md` |

### Existing Command Repair

| Assumption | Confidence | Evidence |
|------------|------------|----------|
| Repair the existing `parse-ownership-bronze` command rather than adding a new command. | Confident | `edgar_warehouse/cli.py`, `edgar_warehouse/application/commands/parse_ownership_bronze.py`, `edgar_warehouse/application/warehouse_orchestrator.py` |
| Fix current silver schema references from `form_type`/`period_of_report` to `form`/`report_date`. | Confident | `edgar_warehouse/silver_store.py`, `edgar_warehouse/application/warehouse_orchestrator.py` |
| Prefer artifact-registry based reads when available, with path-based lookup only as fallback. | Likely | `_run_parse_pipeline` in `edgar_warehouse/application/warehouse_orchestrator.py`, `sec_raw_object` and `sec_filing_attachment` in `edgar_warehouse/silver_store.py`, bronze path templates in `edgar_warehouse/config/warehouse_paths.properties` |

### Bronze Artifact Prerequisite

| Assumption | Confidence | Evidence |
|------------|------------|----------|
| The independent repair is possible only when primary XML already exists in bronze; otherwise report the missing-artifact gap instead of fetching SEC data. | Confident | `edgar_warehouse/cli.py`, `edgar_warehouse/application/warehouse_orchestrator.py`, `.planning/workstreams/neo4j-pipe/REQUIREMENTS.md` |

### MDM Source Validation

| Assumption | Confidence | Evidence |
|------------|------------|----------|
| MDM preflight should fail clearly when source silver is missing or ownership tables are empty. | Confident | `edgar_warehouse/mdm/cli.py`, `.planning/workstreams/neo4j-pipe/REQUIREMENTS.md`, `.planning/workstreams/neo4j-pipe/v1.1-MILESTONE-AUDIT.md` |
| Nonzero `sec_company`, `sec_company_filing`, and `sec_ownership_reporting_owner` rows are required before company-person Neo4j validation is meaningful. | Confident | `edgar_warehouse/mdm/pipeline.py`, `scripts/ops/check-neo4j-e2e.py`, `.planning/workstreams/neo4j-pipe/v1.1-MILESTONE-AUDIT.md` |

## Corrections Made

No corrections -- all assumptions confirmed by the user.
