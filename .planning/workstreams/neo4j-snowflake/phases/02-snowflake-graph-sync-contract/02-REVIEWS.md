---
phase: 2
reviewers: [codex]
reviewed_at: 2026-05-26T23:32:11Z
plans_reviewed:
  - 02-01-PLAN.md
  - 02-02-PLAN.md
  - 02-03-PLAN.md
current_high: 2
---

# Cross-AI Plan Review - Phase 2

## Codex Review

I reviewed only the three Phase 2 plan files under `.planning/workstreams/neo4j-snowflake/phases/02-snowflake-graph-sync-contract`.

### 02-01 Plan

**Summary** - Strong contract-first plan. It correctly starts with SQL-generation tests, narrows scope to Snowflake graph projections, and keeps external Neo4j credentials out of the Phase 2 path. Main risk is that the contract is still partly string-assertion based and may under-specify production details like grants, env-specific database names, and exact property allowlists.

**Strengths**
- Good dependency position: establishes table/view contract before executor and CLI wiring.
- Covers canonical `MDM_GRAPH_NODES` / `MDM_GRAPH_EDGES` plus Native App-compatible `GRAPH_NODE_*` / `GRAPH_EDGE_*`.
- Explicitly preserves stable IDs, active/non-quarantined filtering, provenance, timestamps, and sync status.
- Good credential boundary: generated SQL and README must avoid `NEO4J_*`.

**Concerns**
- **MEDIUM**: Hard-coded emphasis on `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION` may leak dev assumptions into prod behavior unless tests also prove env/target override rendering.
- **MEDIUM**: "Properties without secrets" is vague. The plan should require an explicit property allowlist or construction rule.
- **MEDIUM**: `CREATE OR REPLACE TABLE` can affect grants and downstream consumers unless ownership/grant behavior is specified.
- **LOW**: String-presence SQL tests may miss malformed SQL, duplicate aliases, invalid joins, or incorrect filter placement.
- **LOW**: Missing endpoint diagnostics are required, but severity/exit semantics are not defined.

**Suggestions**
- Add tests for configurable target database/schema, not only `EDGARTOOLS_DEV`.
- Specify `COPY GRANTS`, views over canonical tables, or grant reapplication expectations.
- Define exact node/edge property fields and explicitly exclude credential/config/env fields.
- Add structural SQL assertions for source joins, active/quarantine predicates, and endpoint joins.

**Risk Assessment** - **Medium**. The scope is right and well-contained, but SQL contract mistakes would cascade into both executor and CLI phases.

### 02-02 Plan

**Summary** - Good middle layer plan that isolates Snowflake connection reuse and graph materialization behind an executor. It addresses the key Phase 2 needs: idempotency, bounded filters, no new secrets, and fake-connection tests. The largest gap is filter validation semantics and runtime execution behavior: transaction handling, counts, statement ordering, and failure reporting need sharper definition.

**Strengths**
- Reuses existing `MDM_SNOWFLAKE_*` / `DBT_SNOWFLAKE_*` model instead of adding a new secret path.
- Protects existing export behavior with regression tests.
- Adds bounded `entity_types`, `relationship_types`, `limit`, and `limit_per_type`.
- Keeps tests credential-free with fake connections/cursors.

**Concerns**
- **HIGH**: "Ignore unknown relationship filters only if the existing registry/source query would naturally return zero rows" is ambiguous and risks silent operator typos.
- **MEDIUM**: Idempotency is tested through SQL shape, but not enough detail is given on unique keys, deterministic ordering, or MERGE predicates.
- **MEDIUM**: `limit_per_type` needs exact SQL semantics, likely deterministic `ROW_NUMBER() OVER (PARTITION BY type ORDER BY stable_id)`.
- **MEDIUM**: Result counts require live `SELECT COUNT(*)` queries or returned cursor results, but statement order and error handling are not specified.
- **LOW**: Cursor/connection cleanup, commit/rollback, and partial failure behavior are not called out.

**Suggestions**
- Fail closed on unknown entity/relationship filters using a known registry or generated allowlist.
- Require deterministic ordering for all limited queries.
- Specify executor statement phases: schema setup, materialization, projections, validation/count queries.
- Add fake-cursor tests for count-query execution, exception propagation, and connection cleanup.

**Risk Assessment** - **Medium-High**. The design is sound, but executor ambiguity is where most production bugs would land: silent empty syncs, partial writes, misleading counts, or nondeterministic repair limits.

### 02-03 Plan

**Summary** - Solid CLI integration plan that keeps the operator command surface intact while replacing Bolt writes with Snowflake graph materialization. It has good tests for argument forwarding and `NEO4J_*` absence. The main operational risk is `load-relationships` behavior: routing post-derivation graph sync to Snowflake by default could break existing relationship-loading workflows when Snowflake env is unavailable.

**Strengths**
- Preserves existing `sync-graph` command shape while adding `--entity-type`.
- Tests no external Neo4j dependency directly.
- JSON output with target schema, counts, and filters is appropriate for ECS/operator logs.
- Defers `verify-graph` and traversal checks to Phase 3, avoiding scope creep.

**Concerns**
- **HIGH**: If `load-relationships` automatically syncs to Snowflake when `--skip-graph-sync` is false, existing relationship derivation may now fail due to missing Snowflake credentials.
- **MEDIUM**: Target override flags are useful but increase tampering risk unless executor validation errors are surfaced clearly.
- **MEDIUM**: CLI tests monkeypatching the executor may miss integration issues in config construction from env/defaults.
- **LOW**: JSON output schema is not explicitly named or frozen, which may make downstream automation brittle.
- **LOW**: Help text for remaining Neo4j commands may still confuse operators if Phase 2 partially migrates graph behavior.

**Suggestions**
- Decide explicitly whether `load-relationships` should default to no graph write unless Snowflake sync is requested, or document the breaking behavior.
- Add one CLI test for real config construction with env vars, still without opening a Snowflake connection.
- Define stable JSON keys for `sync-graph` output.
- Ensure executor/config exceptions map to clear nonzero CLI errors without printing secrets.

**Risk Assessment** - **Medium**. CLI scope is controlled, but default behavior around `load-relationships` could create operator-facing regressions.

**Overall Assessment**

The three plans are coherent, correctly ordered, and generally achieve Phase 2 goals for `SYNC-01`, `SYNC-02`, `SYNC-03`, `SNOW-02`, and `SNOW-04`. The strongest qualities are scope control, credential isolation, TDD sequencing, and preservation of bounded repair workflows. The main risks are underspecified Snowflake execution semantics, filter validation ambiguity, dev-environment naming assumptions, and possible behavior changes to `load-relationships`. Addressing those before execution would materially reduce implementation risk.

---

## Consensus Summary

Only the requested Codex reviewer was invoked for this cycle, so consensus is synthesized from recurring themes within that review rather than agreement across multiple reviewers.

### Agreed Strengths

- The Phase 2 plans are correctly ordered: SQL contract, reusable executor, then CLI wiring.
- Scope is well contained to AWS/Snowflake graph materialization and avoids external Neo4j credential dependence for `sync-graph`.
- Credential-free tests and bounded repair workflows are consistently represented across the plan set.

### Agreed Concerns

- **HIGH**: Relationship filter handling in 02-02 is ambiguous and may silently turn operator typos into empty or misleading sync runs.
- **HIGH**: 02-03 may change `load-relationships` behavior so relationship derivation fails when Snowflake credentials are unavailable and graph sync is not explicitly skipped.
- **MEDIUM**: Snowflake execution semantics need sharper detail around idempotency keys, deterministic limiting, counts, statement order, errors, and connection cleanup.
- **MEDIUM**: The contract over-indexes on `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION`; tests should also prove target override and prod-safe rendering behavior.
- **MEDIUM**: Property construction should be explicit enough to prevent accidental inclusion of secrets or unstable fields.

### Divergent Views

- None. This cycle used only the requested Codex reviewer.

## Current HIGH Concerns

- **HIGH**: Relationship filter handling in 02-02 is ambiguous: "ignore unknown relationship filters only if the existing registry/source query would naturally return zero rows" risks silent operator typos.
- **HIGH**: 02-03 may make `load-relationships` automatically sync to Snowflake when `--skip-graph-sync` is false, causing existing relationship derivation workflows to fail when Snowflake credentials are absent.
