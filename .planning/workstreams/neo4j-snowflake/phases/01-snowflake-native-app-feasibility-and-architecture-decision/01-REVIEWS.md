---
phase: 1
reviewers: [codex]
reviewed_at: 2026-05-26T00:36:40Z
plans_reviewed:
  - 01-01-PLAN.md
  - 01-02-PLAN.md
  - 01-03-PLAN.md
---

# Cross-AI Plan Review - Phase 1

## Codex Review

### Summary

The Phase 1 plans are well scoped as documentation and architecture decision work. They preserve the workstream boundary, avoid source edits, and translate the milestone decision into useful runbook, ADR, projection contract, and review-question artifacts. The plan set is not ready to converge yet because two core feasibility outputs can be produced from planning assumptions alone: the graph projection contract does not require reading the current MDM graph schema/code, and the credential/configuration decision does not require mapping the existing `NEO4J_*` command path onto the repository's Snowflake runtime configuration. That leaves Phase 2 with room to guess about exactly the surfaces Phase 1 is supposed to settle.

### Strengths

- The phase boundary is clear: Phase 1 creates workstream-local planning documents only and does not edit source, Terraform, dashboard files, generated JSON, or sibling workstreams.
- Plan waves are sensible. The runbook and ADR can proceed in parallel, and the graph projection contract correctly depends on those outputs.
- The plans preserve the user's cutover decision: Snowflake Marketplace Neo4j Graph Analytics Native App is the target, external Neo4j parallel validation is out of scope, and `edgar-warehouse mdm sync-graph` remains the operator command surface.
- Required Native App projection identifiers are called out explicitly: `nodeId`, `sourceNodeId`, `targetNodeId`, `defaultTablePrefix`, `nodeTables`, and `relationshipTables`.
- Threat models are present and relevant for planning artifacts: privilege broadening, stale external credentials, graph input tampering, and verification repudiation are called out.

### Concerns

- HIGH: `01-03-PLAN.md` can define the graph projection contract without reading the actual MDM relationship schema, graph sync implementation, or existing Snowflake graph migration tests. DISC-04 asks for a confirmed contract for nodes, edges, labels, relationship types, and projection inputs, but the plan only reads planning docs and the ADR. It should require read-only inspection of current source-of-truth files such as `edgar_warehouse/mdm/migrations/runtime.py`, `edgar_warehouse/mdm/migrations/002_seed_data.sql`, `edgar_warehouse/mdm/graph.py`, `edgar_warehouse/mdm/snowflake_graph.py`, `tests/mdm/test_graph.py`, and `tests/mdm/test_snowflake_graph_migration.py`. Otherwise the executor can produce plausible `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES` docs that do not match current entity IDs, relationship type names, dedupe keys, active-state semantics, or existing Snowflake graph fixtures.

- HIGH: `01-02-PLAN.md` can write the credential/configuration ADR without mapping the current external Neo4j runtime path to the existing Snowflake runtime path. The repository currently has command behavior around `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, and `NEO4J_SECRET_JSON` in `edgar_warehouse/mdm/cli.py`, while the milestone requires graph access to come from Snowflake-managed app roles, grants, database roles, and Snowflake connection context. The ADR plan should require read-only inspection of `edgar_warehouse/mdm/cli.py`, `edgar_warehouse/infrastructure/warehouse_settings.py`, `edgar_warehouse/serving/targets/snowflake.py`, Snowflake Terraform access roots, and AWS MDM deploy scripts so it can name the concrete future config handoff. Without that, Phase 2 may inherit an abstract "Snowflake context" decision but still lack a testable replacement for the current Neo4j secret path.

- MEDIUM: `01-01-PLAN.md` does not require the executor to capture fresh documentation evidence and live-account status separately. The runbook asks for current source URLs and a live-account validation section, but the acceptance criteria also say the document can be reviewed without live Snowflake credentials. That is fine if the runbook explicitly records `not run`, `requires operator`, or `validated in account`, but the plan does not require such status labels. Add an evidence table with source URL, access date, account/region applicability, required privilege, and validation status. This matters because Snowflake Native Apps with Snowpark Container Services may require additional privileges depending on service behavior, such as endpoint or external-access related grants beyond `CREATE COMPUTE POOL` and `CREATE WAREHOUSE`.

- MEDIUM: `01-03-PLAN.md` depends on Wave 1 outputs and lists `01-NATIVE-APP-RUNBOOK.md` and `01-ARCHITECTURE-DECISION.md` in context, but the task does not explicitly fail fast if those files are missing or incomplete. Because the plan is autonomous, add a blocking precondition that `01-01` and `01-02` summaries plus their output documents must exist before writing the projection contract and review checklist.

- LOW: The verification commands in `01-01-PLAN.md` and `01-02-PLAN.md` use `rg` for terms that are intentionally expected in rejected-alternative sections, such as `NEO4J_URI` or `external Neo4j`. The prose says to confirm matches are out-of-scope, but the automated command alone cannot distinguish safe from unsafe mentions. Consider adding source assertions for rejected-alternative section headers or exact phrases like `Rejected Alternatives` and `not milestone validation dependencies`.

### Suggestions

- Update `01-03-PLAN.md` so Task 1 has a mandatory `<read_first>` list covering the current MDM schema, graph registry, graph sync engine, Snowflake graph adapter/tests, and MDM graph tests. The acceptance criteria should require the contract to map current `mdm_relationship_type`, `mdm_relationship_instance`, source/target entity IDs, relationship active state, dedupe index, and property payload semantics to the proposed Snowflake node/edge views.
- Update `01-02-PLAN.md` so the ADR names the exact current Neo4j config inputs and the future Snowflake config/auth surfaces that will replace them. It should explicitly state which current code paths Phase 2 must change and which AWS/Snowflake secrets or env vars remain in use.
- Update `01-01-PLAN.md` to require a source and account-evidence matrix. Each Native App assumption should have a status: documented, validated live, blocked, or operator-required.
- Add a Phase 2 entry gate that blocks implementation until the projection contract has been reconciled with actual MDM schema/code and the credential ADR has been reconciled with current CLI/runtime settings.

### Risk Assessment

Overall risk: HIGH.

The plan set is directionally correct and does not overreach into implementation, but Phase 1 is the architecture de-risking phase. If it produces a projection contract and credential decision without inspecting the current MDM graph schema and current runtime config surfaces, the later implementation phases can still make the wrong cutover assumptions while appearing to satisfy the documentation tasks.

## Consensus Summary

Only the Codex reviewer was invoked for this review cycle, so there is no multi-reviewer consensus.

### Agreed Strengths

- Workstream isolation and documentation-only scope are strong.
- Native App projection terminology is present and aligned with current Neo4j/Snowflake documentation.
- The direct migration decision is clearly represented in the plans.

### Agreed Concerns

- The projection contract needs source-level grounding in current MDM schema and graph sync behavior.
- The credential/configuration ADR needs source-level grounding in current `edgar-warehouse` Neo4j and Snowflake runtime configuration.
- Live-account and documentation validation evidence needs explicit status labels.

### Divergent Views

- None. This was a single-reviewer Codex run.

