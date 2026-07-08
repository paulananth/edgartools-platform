# Phase 5: Node And Populated-Relationship Graph Parity - Context

**Gathered:** 2026-07-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Every MDM node type (company, adviser, person, security, fund, audit_firm) syncs to a
verifiable per-type graph view in Snowflake; the 4 already-populated relationship types
(IS_INSIDER, HOLDS, COMPANY_HOLDS, ISSUED_BY) have proven MDM↔graph parity; and
derivation/sync idempotency is established as a repeatable, automated check — for the full
6 node types and 11 relationship types, not just the 4 currently populated. Requirements:
NODE-01..06, EDGE-01..04, GVER-03.

</domain>

<decisions>
## Implementation Decisions

### Verification surface (NODE-01..06 / EDGE-01..04)

- **D-01:** Extend the existing `mdm verify-graph` CLI command's check list — do NOT create
  a new dedicated command, and do NOT go pytest-only with no operator-facing CLI surface.
  `verify-graph`'s SQL already computes per-type parity (`node_parity` / `relationship_parity`
  in the JSON payload, grouped by `ENTITY_TYPE` / `RELATIONSHIP_TYPE` via
  `_render_verify_node_counts` / `_render_verify_relationship_counts` in
  `edgar_warehouse/mdm/snowflake_graph.py`). NODE-01..06 and EDGE-01..04 are named assertions
  over data `verify()` already returns, not new queries. This keeps `verify-graph` as the
  single atomic gate already wired into the Step Functions `mdm_verify_graph` state and
  `go-live.sh`'s local preflight (`run_hosted_graph_preflight`) — a new command would force
  every caller (Step Functions definition, `go-live.sh`, `run-aws-mdm-e2e.sh`) to add and
  sequence a second gate.
- **D-02:** A `GRAPH_NODE_AUDIT_FIRM` view must be added to `render_graph_tables()` /
  `NODE_TABLES` / `ALLOWED_ENTITY_TYPES` in `edgar_warehouse/mdm/snowflake_graph.py`,
  following the exact same pattern as the existing `GRAPH_NODE_COMPANY` /
  `GRAPH_NODE_PERSON` / `GRAPH_NODE_SECURITY` / `GRAPH_NODE_ADVISER` / `GRAPH_NODE_FUND`
  views. This is required regardless of the verification-surface choice — NODE-06 has
  nothing to check until this view exists.
- **D-03 (considered and rejected):** A new dedicated command (e.g. `mdm verify-node-parity`)
  was researched and explicitly ruled out — it fragments the one gate every caller already
  depends on, for no benefit over extending the existing check list.

### Idempotency proof depth (GVER-03)

- **D-04:** Satisfy GVER-03 with an automated regression test, not a one-time documented
  manual verification. `tests/mdm/test_pipeline_relationships.py` already has this exact
  pattern for the 11 relationship types — `test_relationship_derivation_is_idempotent` and
  `test_all_relationship_types_idempotent` run against a real SQLAlchemy session (not mocks)
  and assert `second[rt]["inserted"] == 0`. This pattern previously caught a real bug (the
  "plateau-fix" regression — a missing `ORDER BY` that let `LIMIT`-bounded reruns never
  advance past already-converted rows — a bug a mock could not have surfaced). Phase 5 must
  extend this proven real-DB pattern to cover the 6 node types (new coverage), and extend the
  existing mocked `FakeGraphCursor` pattern in `test_snowflake_graph_migration.py` for the
  graph-sync (full-rebuild) side.
- **D-05:** Do not treat the earlier ad-hoc live verification from this session (bounded
  `mdm sync-graph` with `{"limit": 100000}`, stable 15,285 nodes / 1,117 edges across two runs)
  as satisfying GVER-03 on its own — it's supporting evidence, not the committed regression
  test this requirement now locks in.

### Environment scope

- **D-06:** Prove and fix NODE-01..06 / EDGE-01..04 / GVER-03 in dev (AWS account
  `690839588395`, Snowflake `EDGARTOOLS_DEV`) first. Once dev is green, add an explicit step
  that replicates the same fix/config into `EDGARTOOLS_PRODB` (same AWS account boundary,
  `690839588395`) spanning AWS (ECS task defs / Step Functions), the Snowflake-hosted Neo4j
  Graph Analytics Native App, the Snowflake-native MDM Postgres instance, and the Snowflake
  gold/graph schema — using the existing, already-documented deploy tooling
  (`infra/scripts/deploy-aws-application.sh`, `infra/scripts/deploy-snowflake-stack.sh`,
  the `mirror-mdm-to-snowflake.sh` pattern from this session, and
  `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql`'s activation calls). This is NOT
  new deployment tooling — it's applying tooling that already exists and was already used
  earlier this session to bootstrap prodb.
- **D-07 (safety-critical, explicitly confirmed with the user):** "Prod" in this phase's scope
  means `EDGARTOOLS_PRODB` only. Real production — AWS account `077127448006` and Snowflake
  `EDGARTOOLS_PROD` — must NEVER be touched by this phase's work. This is a standing hard
  constraint from CLAUDE.md/session context, re-confirmed directly for this phase because the
  word "prod" is ambiguous and safety-critical in this repo.

### Claude's Discretion

- Exact SQL/test file layout for the new per-type assertions and idempotency test extensions
  (which functions to add, how to structure fixture data) — the decisions above lock the
  *approach*, not the literal diffs.
- Ordering of the dev-fix-then-prodb-replicate work within Phase 5's plan waves.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements and roadmap
- `.planning/workstreams/fix-pipelines/REQUIREMENTS.md` — full v2.0 requirement text for NODE-01..06, EDGE-01..04, GVER-03 (and the rest of the milestone, for context on what's out of scope this phase)
- `.planning/workstreams/fix-pipelines/ROADMAP.md` — Phase 5 goal, success criteria, dependencies on/from Phases 6-9

### Graph sync / verify implementation
- `edgar_warehouse/mdm/snowflake_graph.py` — `mdm sync-graph` and `mdm verify-graph` implementation; `NODE_TABLES`/`EDGE_TABLES` tuples; `_render_verify_node_counts`/`_render_verify_relationship_counts`; `render_graph_tables()`; the 5 existing `GRAPH_NODE_*` views and 11 `GRAPH_EDGE_*` views
- `edgar_warehouse/mdm/pipeline.py` — the 11 `_derive_*` relationship-derivation methods and `ensure_relationship` upsert pattern
- `edgar_warehouse/mdm/migrations/002_seed_data.sql` and `005_fundamentals_relationships.sql` — canonical entity-type and relationship-type definitions (6 entity types, 11 relationship types)

### Existing test patterns to extend
- `tests/mdm/test_pipeline_relationships.py` — real-DB idempotency test pattern (`test_relationship_derivation_is_idempotent`, `test_all_relationship_types_idempotent`) to extend to node types
- `tests/mdm/test_cli_snowflake_graph.py` — fixture-driven named-check pattern for `verify-graph`'s check list, to extend with per-type assertions
- `tests/mdm/test_snowflake_graph_migration.py` — `FakeGraphCursor` mocked pattern for graph-sync idempotency coverage

### Operator/deploy tooling this phase's environment-scope decision depends on
- `infra/scripts/go-live.sh` — `run_hosted_graph_preflight`, the local preflight that calls `verify-graph`
- `infra/scripts/deploy-aws-application.sh`, `infra/scripts/deploy-snowflake-stack.sh` — existing deploy tooling for replicating fixes to `EDGARTOOLS_PRODB`
- `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql` — Native App activation calls (`CREATE_COMPUTE_POOLS`, `GRANT_CALLBACK`), needed if prodb's Native App isn't already activated
- CLAUDE.md — "Graph storage" and "MDM database" sections (Snowflake-hosted Neo4j Native App and Snowflake-native Postgres, not external services); safety boundary (dev `690839588395` + `EDGARTOOLS_PRODB` only, never real prod)

### Related session findings (background, not this phase's direct scope)
- `.planning/workstreams/claude-mdm-source-recovery/FINDINGS.md` — confirms the canonical dev `silver.duckdb` is healthy (restored this session) and documents the ADV paper-filing dead end relevant to Phase 7's EDGE-07

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_render_verify_node_counts` / `_render_verify_relationship_counts` (`snowflake_graph.py`) already return per-`ENTITY_TYPE`/per-`RELATIONSHIP_TYPE` parity rows — the new NODE-01..06/EDGE-01..04 checks read from this existing payload rather than writing new SQL from scratch.
- `FakeGraphCursor` mock pattern (`test_snowflake_graph_migration.py`) — extend for graph-sync idempotency coverage instead of inventing a new mocking approach.
- Fixture-driven named-check list in `test_cli_snowflake_graph.py` (e.g. `verify_graph:node_counts`, `verify_graph:missing_nodes`) — the established shape for adding new named checks like `verify_graph:node_parity_by_type`.

### Established Patterns
- Graph-sync side is `CREATE OR REPLACE TABLE ... AS SELECT` (full rebuild from current MDM state each run) — idempotency here is largely structural by construction, unlike MDM-side row-by-row upserts.
- MDM relationship derivation uses `ensure_relationship(...)` via a `sync_engine` — an upsert-style pattern that looks up existing rows before inserting.
- `verify-graph` is the single atomic pass/fail gate for graph health, consumed by both the Step Functions `mdm_verify_graph` state and `go-live.sh`'s local preflight — any change here must preserve that single-gate property.

### Integration Points
- `render_graph_tables()`, `NODE_TABLES`, `EDGE_TABLES`, `ALLOWED_ENTITY_TYPES` in `snowflake_graph.py` — where `GRAPH_NODE_AUDIT_FIRM` gets added alongside the existing 5 per-type node views.
- `verify()`'s pass/fail logic (currently `node_parity["status"]=="ok" and relationship_parity["status"]=="ok" and ...`) — where new per-type assertions plug into the existing exit-code gate.

</code_context>

<specifics>
## Specific Ideas

No specific UI/behavior requests — this is backend verification/testing work. The concrete
implementation targets (exact functions, files, and existing patterns to extend) are captured
in `<decisions>` and `<code_context>` above.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 5 scope. The one alternative considered and rejected
(a new dedicated verification command) is recorded under Decisions (D-03) as a rejected
option, not a deferred idea for a future phase — it isn't going anywhere else in the roadmap.

### Reviewed Todos (not folded)

None — `todo.match-phase 5` returned zero matches.

</deferred>

---

*Phase: 5-node-and-populated-relationship-graph-parity*
*Context gathered: 2026-07-08*
