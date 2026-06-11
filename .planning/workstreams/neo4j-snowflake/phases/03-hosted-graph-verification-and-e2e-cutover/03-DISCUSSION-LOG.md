# Phase 3: Hosted Graph Verification And E2E Cutover - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-06-11T10:47:00Z
**Phase:** 3-Hosted Graph Verification And E2E Cutover
**Areas discussed:** Verification depth, Native App smoke test, Snowflake app grants, AWS E2E cutover

---

## Verification Depth

| Question | Alternatives Considered | User's Choice |
|----------|-------------------------|---------------|
| What must `edgar-warehouse mdm verify-graph` prove for Phase 3 to count as complete? | Basic node/edge count vs strict parity gate | Strict parity gate |
| Should a missing or failing Snowflake Native App check make `verify-graph` fail hard? | Fail hard vs separate optional proof | Fail hard |
| Should the command require exact parity between active MDM rows and Snowflake graph rows? | Exact parity vs count-only or tolerance-based validation | Exact parity |
| Should `verify-graph` emit structured diagnostics grouped by node class and relationship type with sample IDs? | Structured diagnostics vs simple failure text | Structured diagnostics |

**User's choice:** `verify-graph` must be the strict Phase 3 gate with SQL parity, Native App proof, and actionable diagnostics.
**Notes:** User answered yes to Native App failure, exact parity, and structured diagnostics.

---

## Native App Smoke Test

| Question | Alternatives Considered | User's Choice |
|----------|-------------------------|---------------|
| Should the smoke test require both `GRAPH_INFO` metadata proof and real graph execution? | Metadata only, algorithm only, or both | Both |
| Should Phase 3 prefer deterministic `BFS` or graph-wide `WCC`? | `BFS`, `WCC`, or both | Both |
| Should the smoke test create missing Native App prerequisites automatically when possible? | Auto-create safe prerequisites vs fail with manual-only remediation | Auto-create safe prerequisites and document the rest |
| Should the Native App smoke test run by default inside `verify-graph`? | Default-on vs separate command or opt-in | Default-on, with opt-out only for local/offline tests |

**User's choice:** Native App smoke proof must include `GRAPH_INFO`, `BFS`, and `WCC`; it runs by default through `verify-graph`.
**Notes:** User specifically said anything missing should be documented properly.

---

## Snowflake App Grants

| Question | Alternatives Considered | User's Choice |
|----------|-------------------------|---------------|
| Should Phase 3 define a dedicated database role for graph schema access and grant it to the Native App? | Dedicated database role vs rely on `ACCOUNTADMIN` ownership | Dedicated database role |
| Should grants be managed by repo automation or only documented manually? | Repo automation plus docs vs manual-only setup | Repo automation plus docs |
| Should grants be least-privilege read-only rather than broad ownership/account grants? | Least-privilege read-only vs broad grants | Least-privilege read-only |
| Should grant validation become part of `verify-graph`? | Fail with exact remediation vs external/manual validation | Fail with exact remediation |

**User's choice:** Phase 3 must automate least-privilege Native App grants and validate them in `verify-graph`.
**Notes:** Live investigation found no database roles in `EDGARTOOLS_DEV` and no grants to the Native App, so this is a required planning target.

---

## AWS E2E Cutover

| Question | Alternatives Considered | User's Choice |
|----------|-------------------------|---------------|
| Should AWS MDM E2E remove external Neo4j connectivity as a success requirement and replace it with Snowflake `sync-graph` plus strict `verify-graph`? | Snowflake-hosted success path vs external Neo4j connectivity gate | Snowflake-hosted success path |
| Should AWS E2E fail if deployed MDM task definitions or scripts still require `NEO4J_*` secrets/env vars? | Fail hard vs warning only | Warning only |
| Should AWS E2E proof include Step Functions execution validation? | Step Functions validation vs local/script-level proof only | Step Functions validation |
| Should final Phase 3 acceptance require a documented live dev run with `SNOW_CONNECTION=snowconn`, `DBT_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV`, and AWS dev deployment outputs? | Required live dev run vs local-only proof | Required live dev run |

**User's choice:** AWS E2E success moves to Snowflake `sync-graph` plus strict `verify-graph`, includes Step Functions validation, and captures a non-secret live dev run.
**Notes:** Stale `NEO4J_*` references are warnings only unless they remain functional blockers or success gates for the Snowflake-hosted path.

## the agent's Discretion

No discussion areas were delegated fully to the agent.

## Deferred Ideas

None.
