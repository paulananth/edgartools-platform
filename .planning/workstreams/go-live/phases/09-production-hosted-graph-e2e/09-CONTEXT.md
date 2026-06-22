# Phase 9: Production Hosted Graph E2E - Context

**Gathered:** 2026-06-21
**Status:** Ready for planning
**Source:** Codex handoff + Phase 8 evidence review

<domain>
## Phase Boundary

Phase 9 proves the production hosted graph path after Phase 7 and Phase 8.
It does not redo production Snowflake native-pull/dbt, does not rotate or
populate MDM secrets, and does not broaden the graph architecture.

This phase has two execution plans:

1. **09-01: Native App prerequisites, bounded local MDM graph sync, and strict verify.**
   Provision or repair the production Neo4j Graph Analytics Native App grants
   and compute-pool availability, run a bounded production MDM data smoke if
   the fresh Phase 8 database is still empty, run `mdm sync-graph`, and pass
   strict `mdm verify-graph`.
2. **09-02: AWS MDM hosted graph E2E.**
   Run the production AWS MDM Step Functions chain with the script's default
   local strict preflight, then update the launch gate matrix only after both
   Phase 8 and Phase 9 proof exists.

Production MDM secrets and application-role connectivity are already complete
via Phase 8 / PR #80. Phase 9 consumes `edgartools-prod/mdm/postgres_dsn` and
`edgartools-prod/mdm/snowflake`; it must not rotate, print, or repopulate them.

</domain>

<decisions>
## Implementation Decisions

### Phase 8 Boundary
- **D-01:** Phase 8 is complete and merged via PR #80. Phase 9 must not rerun
  `bootstrap-prod-mdm.sh`, rotate Postgres credentials, populate
  `edgartools-prod/mdm/postgres_dsn`, or populate
  `edgartools-prod/mdm/snowflake`.
- **D-02:** Phase 9 treats the Phase 8 evidence file as the source of truth for
  secret population and Postgres application-role connectivity. The executor
  may read secret metadata with `describe-secret`, but never reads secret
  values except inside a single non-printing shell invocation that directly
  runs the consuming CLI.
- **D-03:** The `edgartools-prod/mdm/snowflake` secret is functionally verified
  in this phase by the `sync-graph`/`verify-graph` path. Phase 8 only
  presence-verified it.

### Native App Production Target
- **D-04:** The production graph target is Snowflake database
  `EDGARTOOLS_PROD`, graph schema `NEO4J_GRAPH_MIGRATION`, MDM schema `MDM`,
  Native App `Neo4j_Graph_Analytics`, database role
  `NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE`, and default compute pool selector
  `CPU_X64_XS` unless live `SHOW_AVAILABLE_COMPUTE_POOLS()` proves a different
  operator-approved selector is required.
- **D-05:** The existing grants SQL file is dev-scoped. Phase 9 may use it as a
  template, but any production grant/provisioning run must target
  `EDGARTOOLS_PROD` explicitly and must not accidentally reapply dev grants as
  prod proof.
- **D-06:** Native App provisioning is state-changing Snowflake work. It
  requires explicit operator approval before execution. A read-only metadata
  check may run before approval; grants, compute-pool creation/activation, and
  graph algorithm invocations may not.

### Bounded Graph Smoke
- **D-07:** Phase 8 final counts were expectedly zero because the production MDM
  database was fresh. If Phase 9 still finds zero usable MDM graph rows, the
  executor may run a bounded production MDM smoke before graph sync:
  `mdm run --entity-type all --limit 5` and
  `mdm backfill-relationships --limit 100`, with explicit operator approval.
- **D-08:** Phase 9 never runs a full bootstrap or unbounded backfill by
  default. All production data writes in this phase must have explicit limits
  and stop conditions.
- **D-09:** `mdm sync-graph` must run with an explicit bound, defaulting to
  `--limit 100`, against the production MDM database and production Snowflake
  graph target.
- **D-10:** `mdm verify-graph` is the local acceptance gate. PASS requires
  `status: ok`, SQL parity checks, `native_app.status: ok`, compute-pool
  availability, `graph_info`, `bfs`, and `wcc` checks.

### AWS E2E
- **D-11:** `infra/scripts/run-aws-mdm-e2e.sh --env prod` is the AWS E2E driver.
  It must run with default preflight enabled. `--skip-preflight` is not a
  launch-gate pass and is not used for Phase 9 acceptance.
- **D-12:** The AWS E2E pass must show all six stages reaching success:
  `mdm_migrate`, `mdm_run`, `mdm_backfill_relationships`,
  `mdm_sync_graph`, `mdm_verify_graph`, and `mdm_counts`.
- **D-13:** The AWS E2E uses the deployer profile for Step Functions
  execution, not AWS admin, unless live permissions prove a different
  already-documented production operator profile is required.

### Evidence And Matrix
- **D-14:** Evidence files record commands, environment labels, pass/fail
  status, graph node/edge counts, parity status, Native App check names, Step
  Functions stage names/statuses, and remediation summaries only.
- **D-15:** Evidence must not include DSNs, passwords, tokens, Terraform state,
  raw connector traces, raw Native App job logs, raw Step Functions cause
  strings, full generated application JSON, S3 URLs, account locators, or image
  digests.
- **D-16:** The Phase 8 MDM row and Phase 9 graph rows in
  `01-LAUNCH-GATE-MATRIX.md` are flipped to PASS only after Phase 9 passes.
  The final matrix edit must reference both Phase 8 evidence and Phase 9
  hosted-graph/AWS E2E evidence.

### the agent's Discretion
- The executor may choose a local temp SQL file or direct `snow sql` statements
  for production Native App grants, as long as the target database/schema are
  explicit, the command is reviewed before state change, and only sanitized
  evidence is committed.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Workstream Contracts
- `.planning/workstreams/go-live/PROJECT.md` - v1.6 launch goal,
  AWS/Snowflake-only boundary, and production evidence contract.
- `.planning/workstreams/go-live/REQUIREMENTS.md` - GRAPH-03, GRAPH-04,
  SEC-02, and ISO-03 requirement definitions.
- `.planning/workstreams/go-live/ROADMAP.md` - Phase 9 goal, dependencies,
  plan labels, and success criteria.
- `.planning/workstreams/go-live/STATE.md` - blocker list and decision that
  `edgar-warehouse mdm verify-graph` remains the hosted graph acceptance gate.

### Completed Inputs
- `.planning/workstreams/go-live/phases/07-production-snowflake-native-pull-and-gold/evidence/native-pull.md`
  - SNOW-03 production native-pull PASS evidence.
- `.planning/workstreams/go-live/phases/07-production-snowflake-native-pull-and-gold/evidence/dbt-gold.md`
  - SNOW-04 production dbt/gold PASS evidence.
- `.planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md`
  - Phase 8 production MDM secrets, migration, grants, and connectivity proof.
- `infra/scripts/bootstrap-prod-mdm.sh` - one-click Phase 8 rerun script;
  read for the non-printing credential-pipeline contract, but do not rerun for
  Phase 9.

### Graph Implementation And Drivers
- `infra/scripts/run-aws-mdm-e2e.sh` - AWS MDM E2E driver and strict local
  preflight behavior.
- `edgar_warehouse/mdm/cli.py` - `mdm run`, `backfill-relationships`,
  `sync-graph`, `verify-graph`, and `counts` CLI behavior.
- `edgar_warehouse/mdm/export.py` - `SnowflakeConnectionSettings.from_env()`
  and secret/env resolution for the MDM Snowflake secret.
- `edgar_warehouse/mdm/snowflake_graph.py` - graph sync defaults, Native App
  verification checks, `GRAPH_INFO`, `BFS`, and `WCC` calls.
- `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql` - dev-scoped
  Native App grant script used as the template for prod-scoped grants.

### Launch Evidence Targets
- `.planning/workstreams/go-live/milestones/v1.5-phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md`
  - Phase 8 and Phase 9 rows to reconcile after the final graph proof.
- `.planning/workstreams/go-live/milestones/v1.5-phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md`
  - concise launch evidence target for MDM/hosted graph proof.
- `.planning/workstreams/go-live/milestones/v1.5-phases/03-mdm-hosted-graph-e2e-acceptance/03-CONTEXT.md`
  - dev rehearsal precedent and `--skip-preflight` acceptance framing.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `infra/scripts/run-aws-mdm-e2e.sh` already implements the production AWS
  sequence and local strict preflight.
- `edgar_warehouse/mdm/snowflake_graph.py` defaults match the intended prod
  graph target shape except the database is resolved from Snowflake connection
  settings.
- `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql` contains the
  grant categories needed for prod, but is currently hardcoded to `EDGARTOOLS_DEV`.

### Integration Points
- Local graph sync consumes both production secrets: `MDM_DATABASE_URL` for
  Postgres and `MDM_SNOWFLAKE_SECRET_JSON` or Snowflake CLI config for
  Snowflake.
- Strict graph verification can use `SNOW_CONNECTION=edgartools-prod`,
  `DBT_SNOWFLAKE_DATABASE=EDGARTOOLS_PROD`, and
  `--native-app-compute-pool CPU_X64_XS`.
- AWS E2E reads `infra/aws-prod-application.json` and starts the six MDM Step
  Functions state machines listed there.

</code_context>

<specifics>
## Specific Ideas

- Preferred local strict verify command shape:
  `SNOW_CONNECTION=edgartools-prod DBT_SNOWFLAKE_DATABASE=EDGARTOOLS_PROD uv run --extra snowflake edgar-warehouse mdm verify-graph --native-app-compute-pool CPU_X64_XS`
- Preferred AWS E2E command shape:
  `bash infra/scripts/run-aws-mdm-e2e.sh --env prod --aws-profile sec_platform_deployer --aws-region us-east-1 --snow-connection edgartools-prod --snowflake-database EDGARTOOLS_PROD --native-app-compute-pool CPU_X64_XS --mdm-run-limit 5 --graph-limit 100`
- Phase 9 evidence files should live under
  `.planning/workstreams/go-live/phases/09-production-hosted-graph-e2e/evidence/`.

</specifics>

<deferred>
## Deferred Ideas

- Formal removal of legacy external Neo4j runtime remnants remains a future
  requirement after production hosted graph validation is stable.
- Managed dashboard deployment is Phase 10 or later; Phase 9 does not touch
  dashboard launch.

</deferred>

---

*Phase: 09-production-hosted-graph-e2e*
*Context gathered: 2026-06-21 by Codex from user handoff and existing evidence*
