# Phase 1 Pattern Map

**Updated:** 2026-05-25
**Scope:** Planning-only documentation work

## Existing Local Patterns To Preserve

### Workstream-Local Planning Artifacts

Use the existing workstream boundary:

- `.planning/workstreams/neo4j-snowflake/PROJECT.md`
- `.planning/workstreams/neo4j-snowflake/REQUIREMENTS.md`
- `.planning/workstreams/neo4j-snowflake/ROADMAP.md`
- `.planning/workstreams/neo4j-snowflake/STATE.md`

Phase 1 output should stay under:

`.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/`

Do not edit sibling workstreams:

- `.planning/workstreams/mdm-neo4j-dashboard/`
- `.planning/workstreams/neo4j-pipe/`
- `.planning/workstreams/fix-pipelines/`

### AWS/Snowflake Documentation Style

The repo's AWS/Snowflake guidance uses operator-oriented runbooks with explicit commands,
inputs, outputs, and gotchas. Phase 1 documents should follow that style: state what an
operator must do, which role does it, what privilege is granted, and what proves success.

Relevant local references:

- `AGENTS.md` - AWS/Snowflake platform guidance.
- `.planning/workstreams/neo4j-snowflake/PROJECT.md` - Native App milestone architecture.
- `.planning/workstreams/neo4j-snowflake/REQUIREMENTS.md` - Phase 1 requirement IDs.

### Future Implementation Boundaries

Phase 1 should not edit source code, but it should name the future implementation surfaces
so Phase 2 and later plans do not rediscover them:

- `edgar_warehouse/mdm/cli.py` - future command surface for `mdm sync-graph` and `mdm verify-graph`.
- `edgar_warehouse/mdm/graph.py` - likely legacy external Neo4j graph integration surface.
- `infra/snowflake/dbt/edgartools_gold/` - existing Snowflake model area to reuse rather than redesign.
- `infra/scripts/run-aws-mdm-e2e.sh` - future AWS E2E verification path.

These files are read-only references for Phase 1 plans.

## Planned Document Outputs

| Output | Purpose |
|--------|---------|
| `01-NATIVE-APP-RUNBOOK.md` | Operator install, activation, roles, grants, compute pool, warehouse, and live-account validation checklist. |
| `01-ARCHITECTURE-DECISION.md` | Decision record for direct migration from external Neo4j to Snowflake Native App target. |
| `01-GRAPH-PROJECTION-CONTRACT.md` | Proposed node/edge table or view contract and Native App projection inputs. |
| `01-PLAN-REVIEW-QUESTIONS.md` | Questions and risks for plan-review convergence before Phase 2 coding. |

## Non-Patterns

- Do not create or revive non-AWS deployment paths.
- Do not introduce new external Neo4j credentials.
- Do not modify generated application JSON or Terraform state.
- Do not touch dashboard implementation files in Phase 1.
- Do not write source code during Phase 1 execution.
