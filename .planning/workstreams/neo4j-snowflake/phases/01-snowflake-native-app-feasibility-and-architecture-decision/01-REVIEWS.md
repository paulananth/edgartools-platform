---
phase: 1
reviewers: [codex]
reviewed_at: 2026-05-26T00:44:39Z
review_cycle: 2
prior_review_commit: d7e28d5
replan_commit: 257aacb
plans_reviewed:
  - 01-01-PLAN.md
  - 01-02-PLAN.md
  - 01-03-PLAN.md
---

# Cross-AI Plan Review - Phase 1

## Cycle 1 Summary

Cycle 1 found two HIGH concerns:

- `01-03-PLAN.md` could define the graph projection contract without reading the current MDM relationship schema, graph sync implementation, or existing Snowflake graph migration tests.
- `01-02-PLAN.md` could define the credential/configuration ADR without mapping the current `NEO4J_*` CLI path to existing Snowflake runtime and auth surfaces.

The follow-up replan in commit `257aacb` updated `01-02-PLAN.md` and `01-03-PLAN.md`.

## Codex Review - Cycle 2

### Summary

The two cycle-1 HIGH concerns are fully resolved by the replanned Phase 1 plans. `01-02-PLAN.md` now requires the architecture decision record to inspect the concrete current Neo4j command path in `edgar_warehouse/mdm/cli.py`, including `_neo4j_client()`, `NEO4J_URI`, `NEO4J_USER`/`NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, and `NEO4J_SECRET_JSON`, and to map that path to existing Snowflake runtime surfaces such as `MDM_SNOWFLAKE_*`, `DBT_SNOWFLAKE_*`, `SERVING_EXPORT_ROOT`, `SNOWFLAKE_EXPORT_ROOT`, Snowflake export code, Snowflake access grants, and AWS MDM deployment/e2e scripts. `01-03-PLAN.md` now requires the graph projection contract to read the actual MDM schema, seeded relationship registry, graph sync engine, hosted Snowflake graph migration generator, and tests before defining the Native App-facing node/edge contract. That is enough source grounding for Phase 1 planning convergence.

### Strengths

- `01-02-PLAN.md` now names the current external Neo4j environment variables and consuming handlers instead of using an abstract credential model.
- `01-02-PLAN.md` explicitly requires the ADR to identify Phase 2 source-change targets: `_neo4j_client()`, `sync-graph`, `verify-graph`, graph connectivity checks, and graph sync call sites that expect `Neo4jGraphClient`.
- `01-02-PLAN.md` preserves the correct boundary: Phase 1 records the decision, while source code and Terraform changes remain out of scope.
- `01-03-PLAN.md` now reads `edgar_warehouse/mdm/migrations/runtime.py`, `002_seed_data.sql`, `graph.py`, `snowflake_graph.py`, `tests/mdm/test_graph.py`, and `tests/mdm/test_snowflake_graph_migration.py` before writing the projection contract.
- `01-03-PLAN.md` now requires reconciliation between proposed `MDM_GRAPH_NODES`/`MDM_GRAPH_EDGES` and the existing `GRAPH_NODES`/`GRAPH_EDGES` generator and tests, including column casing differences between current Snowflake SQL and Native App documentation.
- `01-03-PLAN.md` adds fail-fast dependencies on `01-NATIVE-APP-RUNBOOK.md`, `01-ARCHITECTURE-DECISION.md`, `01-01-SUMMARY.md`, and `01-02-SUMMARY.md` before Wave 2 writes the graph contract.

### Prior HIGH Resolution

| Prior Concern | Cycle 2 Status | Evidence |
| --- | --- | --- |
| `01-03-PLAN.md` could define the projection contract without source-grounding in MDM schema/code/tests. | Fully resolved | The plan now requires read-only inspection of the MDM migration runtime, seed data, graph sync engine, Snowflake graph generator, graph tests, and Snowflake graph migration tests. It also requires the contract to map `mdm_relationship_type`, `mdm_relationship_instance`, seeded relationship types, `source_entity_id`, `target_entity_id`, `properties`, `graph_synced_at`, `is_active`, and `idx_rel_instance_dedup`. |
| `01-02-PLAN.md` could define the credential/configuration ADR without mapping the current external Neo4j path to existing Snowflake runtime/auth surfaces. | Fully resolved | The plan now requires read-only inspection of `edgar_warehouse/mdm/cli.py`, `edgar_warehouse/mdm/export.py`, `warehouse_settings.py`, `serving/targets/snowflake.py`, Snowflake access Terraform, and AWS MDM scripts. It explicitly names current `NEO4J_*`/`NEO4J_SECRET_JSON` inputs and future Snowflake-managed app roles, database roles, grants, warehouse/app warehouse context, and connection context. |

### Concerns

- MEDIUM: `01-01-PLAN.md` still allows the Native App runbook to be reviewed without live Snowflake credentials, which is acceptable for Phase 1 planning, but the eventual runbook must label each account-dependent check as documented, validated live, blocked, or operator-required. This is not a convergence blocker because Phase 3 carries live validation and the plan already has a `Live Account Validation` section.
- LOW: The `rg` verification in `01-02-PLAN.md` intentionally matches rejected alternatives like `external Neo4j`. Executors should continue to inspect the matched sections, not treat the command alone as proof of correctness.

### Suggestions

- Keep the cycle-2 source-grounding requirements intact during execution. Do not shorten the `read_first` lists in `01-02-PLAN.md` or `01-03-PLAN.md`.
- In execution, make the ADR and projection contract cite exact source file observations so Phase 2 can distinguish settled decisions from open live-account questions.
- Consider carrying the `documented`, `validated live`, `blocked`, and `operator-required` status vocabulary into `01-NATIVE-APP-RUNBOOK.md` during execution.

### Risk Assessment

Overall risk: MEDIUM.

The remaining risk is mostly the expected Phase 1 feasibility risk around live Snowflake Marketplace and Native App account behavior. The earlier HIGH planning risks are resolved because the replanned tasks now force source-level grounding before the ADR and graph projection contract can be written.

## Consensus Summary

Only the Codex reviewer was invoked for this review cycle, so there is no multi-reviewer consensus.

### Agreed Strengths

- The replanned credential/configuration ADR is grounded in current repository code and runtime settings.
- The replanned graph projection contract is grounded in current MDM schema, graph sync behavior, hosted Snowflake graph SQL, and tests.
- The plans preserve workstream isolation and keep Phase 1 documentation-only.

### Agreed Concerns

- Live Snowflake account validation remains a later proof point and must be labeled clearly in Phase 1 outputs.

### Divergent Views

- None. This was a single-reviewer Codex run.
