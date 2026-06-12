# Milestone v1.3 - Project Summary

**Workstream:** `neo4j-snowflake`
**Milestone:** Neo4j Snowflake Native App Migration
**Generated:** 2026-06-12T18:49:12Z
**Purpose:** Team onboarding and project review
**Status:** In progress - Phases 1 through 3 complete, Phase 4 not started

---

## 1. Project Overview

The v1.3 milestone moves Neo4j graph analytics from an external Neo4j runtime into the
Snowflake Marketplace Neo4j Graph Analytics Native App while preserving the existing AWS
and Snowflake platform path.

The target operator workflow is:

```text
SEC EDGAR API
  -> edgar-warehouse CLI on AWS ECS
  -> S3 bronze / warehouse storage
  -> Snowflake source + gold tables
  -> MDM entity and relationship state
  -> Snowflake graph-ready node and edge tables/views
  -> Neo4j Graph Analytics Native App in Snowflake
  -> MDM Neo4j review dashboard
```

The important product decision is that `edgar-warehouse` remains the owner of graph sync
and verification. The graph target changes from external Neo4j/Bolt to Snowflake-hosted
graph tables, Native App roles, Native App grants, and Snowflake connection context.

Current progress is 75% of the milestone:

- Phase 1 complete: feasibility, runbook, architecture decision, and graph projection
  contract.
- Phase 2 complete: Snowflake graph sync materialization and CLI wiring.
- Phase 3 complete: strict hosted graph verification and AWS MDM E2E cutover accepted in
  live dev.
- Phase 4 pending: dashboard migration to inspect the Snowflake-hosted graph target.

## 2. Architecture & Technical Decisions

- **Decision:** Use the Snowflake Marketplace Neo4j Graph Analytics Native App as the
  milestone graph target.
  **Why:** The milestone is a direct migration from external Neo4j to a Snowflake-hosted
  graph analytics path, not a dual-write or parallel external validation project.
  **Phase:** 1.

- **Decision:** Keep `edgar-warehouse mdm sync-graph` as the operator command surface.
  **Why:** Operators already use the MDM CLI for graph sync; the implementation should
  change the graph target, not create a second workflow.
  **Phase:** 1 and 2.

- **Decision:** Replace external `NEO4J_*` milestone validation with Snowflake-managed
  app roles, database roles, grants, warehouse/app context, compute-pool privileges, and
  Snowflake connection context.
  **Why:** The Native App path should be governed through Snowflake, and Phase 3
  acceptance must not depend on external Aura/Bolt credentials.
  **Phase:** 1 through 3.

- **Decision:** Materialize canonical `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES`, with
  compatibility `GRAPH_NODES` / `GRAPH_EDGES` views and per-label/per-type
  `GRAPH_NODE_*` / `GRAPH_EDGE_*` projections.
  **Why:** This preserves the MDM relationship source of truth while giving the Native
  App stable Snowflake-facing graph inputs.
  **Phase:** 2.

- **Decision:** `verify-graph` is a hard gate, not a warning-only report.
  **Why:** Phase 3 acceptance requires exact MDM-to-Snowflake graph parity plus Native
  App proof through `GRAPH_INFO`, `BFS`, and `WCC`.
  **Phase:** 3.

- **Decision:** AWS MDM E2E preflights strict local hosted `verify-graph` before
  starting full Step Functions runs.
  **Why:** This prevents spending AWS execution time on a run that cannot satisfy Phase
  3 acceptance because Native App prerequisites are missing.
  **Phase:** 3.

## 3. Phases Delivered

| Phase | Name | Status | One-Liner |
| --- | --- | --- | --- |
| 1 | Snowflake Native App Feasibility And Architecture Decision | Complete | Documented the Marketplace app runbook, accepted the direct migration ADR, and defined the graph projection contract. |
| 2 | Snowflake Graph Sync Contract | Complete | Replaced external Neo4j graph sync with Snowflake graph materialization under the existing MDM CLI surface. |
| 3 | Hosted Graph Verification And E2E Cutover | Complete | Made `verify-graph` a strict Snowflake-hosted parity and Native App proof gate, then accepted AWS hosted graph E2E in live dev. |
| 4 | Dashboard Hosted Graph Migration | Not started | Migrate the existing review dashboard to compare MDM state with the Snowflake-hosted graph target. |

## 4. Requirements Coverage

Completed:

- DISC-01 through DISC-04: Native App install/validation, architecture decision,
  Snowflake-managed credential model, and graph projection contract.
- SYNC-01 through SYNC-04: Snowflake graph materialization, idempotent counts, bounded
  filters, and hosted `verify-graph`.
- SNOW-01 through SNOW-04: Native App grants/runbook, graph projections from existing
  Snowflake/MDM state, query-level Native App checks, and governed output behavior.
- VERIFY-01, VERIFY-02, VERIFY-03, VERIFY-05: node parity, relationship parity,
  traversal-style Native App proof, and AWS E2E validation.
- ISO-01 and ISO-02: workstream isolation and AWS/Snowflake-only scope.

Pending:

- VERIFY-04: dashboard comparison against the Snowflake-hosted graph target.
- DASH-01: use the existing MDM Neo4j review dashboard against the Snowflake-hosted graph.
- DASH-02: show bounded MDM-to-Snowflake graph mismatch views without mutation.
- DASH-03: remove stale external Neo4j credential assumptions from dashboard configuration
  and errors.

Live Phase 3 acceptance evidence:

- Strict local hosted graph gate returned `status: ok`.
- Snowflake graph nodes: `15`.
- Snowflake graph edges: `4`.
- Node parity and relationship parity: `ok`.
- Missing/extra node, edge, and endpoint diagnostics: none.
- Native App compute pool: `CPU_X64_XS`.
- `GRAPH_INFO`, `BFS`, and `WCC`: `ok`.
- Latest AWS hosted graph E2E executions `aws-mdm-e2e-1781277675-*` succeeded for
  `mdm_migrate`, `mdm_run`, `mdm_backfill_relationships`, `mdm_sync_graph`,
  `mdm_verify_graph`, and `mdm_counts`.

## 5. Key Decisions Log

- **D-01 Native App Target:** The Snowflake Marketplace Neo4j Graph Analytics Native App
  is the target graph runtime for this milestone.
- **D-02 Production Migration Direction:** This is a production migration path with
  feasibility and architecture before implementation.
- **D-03 edgar-warehouse Ownership:** `edgar-warehouse mdm sync-graph` remains the graph
  sync command surface.
- **D-04 No External Neo4j Parallel Target:** External Neo4j is not retained as a
  parallel validation target for this milestone.
- **D-05 Snowflake-Managed Graph Access:** Graph access moves to Snowflake app roles,
  database roles, grants, compute-pool/application privileges, and Snowflake connection
  context.
- **D-06 Existing Snowflake Model Reuse:** Graph projection work reuses existing
  Snowflake source/gold and MDM graph models where possible.
- **D-07 Verification Standard:** Acceptance requires node count parity, edge parity,
  traversal/connectivity proof, dashboard comparison, and AWS E2E proof.
- **D-08 Workstream Isolation:** Artifacts stay under
  `.planning/workstreams/neo4j-snowflake/` unless explicitly merged.

## 6. Tech Debt & Deferred Items

- Phase 4 remains open. The dashboard still needs to move from external Neo4j review
  assumptions to Snowflake-hosted graph comparison.
- Stale deployment/script references to `NEO4J_*`, `neo4j`, `--neo4j`, and
  `mdm_check_connectivity` remain warning-only unless they block the hosted graph path.
- External Neo4j runtime support still needs a post-milestone decision: remove,
  deprecate, or retain only for local development.
- Future work should add graph analytics result marts for downstream Snowflake dashboard
  use.
- Future work should add production cost and compute-pool monitoring for Neo4j Graph
  Analytics workloads.
- The Native App compute-pool activation was an operator/Snowsight step, not Terraform.
  Repo automation now documents grants and verifies readiness, but does not own the app's
  internal compute pool lifecycle.

## 7. Getting Started

Read these first:

- `.planning/workstreams/neo4j-snowflake/STATE.md` for current position.
- `.planning/workstreams/neo4j-snowflake/ROADMAP.md` for phase structure.
- `.planning/workstreams/neo4j-snowflake/REQUIREMENTS.md` for requirement coverage.
- `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md` for accepted Phase 3 evidence.

Code entry points:

- `edgar_warehouse/mdm/cli.py` for `sync-graph`, `verify-graph`, and graph-related MDM
  command wiring.
- `edgar_warehouse/mdm/snowflake_graph.py` for graph SQL generation, graph sync, and
  hosted graph verification.
- `infra/scripts/run-aws-mdm-e2e.sh` for AWS hosted graph E2E validation.
- `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql` for repo-managed Native
  App grant setup.
- `tests/mdm/test_cli_snowflake_graph.py` and
  `tests/mdm/test_snowflake_graph_migration.py` for focused graph behavior coverage.

Useful local checks:

```bash
bash -n infra/scripts/run-aws-mdm-e2e.sh
uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q
uv run --extra mdm-runtime pytest tests/mdm/test_cli_snowflake_graph.py tests/mdm/test_snowflake_graph_migration.py tests/mdm/test_export.py -q
```

Useful live Phase 3 regression gate:

```bash
SNOW_CONNECTION=snowconn \
SNOWFLAKE_CONNECTION=snowconn \
DBT_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV \
uv run --extra snowflake edgar-warehouse mdm verify-graph
```

Useful AWS hosted graph E2E command:

```bash
bash infra/scripts/run-aws-mdm-e2e.sh \
  --env dev \
  --aws-profile sec_platform_deployer \
  --snow-connection snowconn \
  --snowflake-database EDGARTOOLS_DEV
```

## Stats

- **Timeline:** 2026-05-26 -> 2026-06-12.
- **Phases:** 3 complete / 4 total.
- **Plans:** 9 complete / 9 planned so far; Phase 4 plans are still TBD.
- **Progress:** 75%.
- **Relevant commits found since 2026-05-26:** 16.
- **Latest Phase 3 PR:** #64, merged as `0fad745`.
- **Latest Phase 3 PR size:** 18 files changed, +2222 / -81.
- **Contributors in relevant git history:** Aneena Ananth, Paul Ananth.

