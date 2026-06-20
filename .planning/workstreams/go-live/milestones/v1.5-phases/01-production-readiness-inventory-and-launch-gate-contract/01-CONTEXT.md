# Phase 1: Production Readiness Inventory And Launch Gate Contract - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase defines the production go-live gate contract. It inventories launch
prerequisites, classifies blockers, defines evidence artifacts, and sets the
rules for what can be trusted before later phases run production deployment,
Snowflake, MDM, hosted graph, or dashboard validation work. It does not execute
the production launch.

</domain>

<decisions>
## Implementation Decisions

### Launch Blocker Rules

- **D-01:** Phase 1 uses a strict gate: missing production proof, unsafe deploy hazards, incomplete acceptance docs, or launch-affecting incomplete workstream closeout are blockers until fixed.
- **D-02:** Incomplete upstream workstream items that affect launch evidence, dashboard docs, acceptance gates, or operator runbooks block go-live until merged and rechecked.
- **D-03:** Known deploy hazards with documented workarounds are blockers until the go-live runbook has explicit required mitigations and the checklist enforces those mitigations before deploy.
- **D-04:** Missing production artifacts or live proof are blockers until discovered live or replaced by explicit operator-provided evidence.
- **D-05:** Warning-only status is allowed only for cleanup that does not affect operator commands, acceptance gates, security, or evidence.
- **D-06:** No waivers are allowed. Launch blockers must be fixed, not waived.
- **D-07:** Secret-safety failures in evidence or runbooks are hard blockers until scrubbed and rechecked.
- **D-08:** A blocker is fixed only after rerunning the relevant check and recording a non-secret pass summary in the Phase 1 inventory.

### Evidence Bundle Format

- **D-09:** Phase 1 should produce one launch gate matrix plus an evidence folder split by domain.
- **D-10:** Command evidence must include exact command, environment label, pass/fail, key counts or statuses, and sanitized evidence links. Full logs should not be pasted.
- **D-11:** Downstream planners should create:
  - `01-LAUNCH-GATE-MATRIX.md`
  - `evidence/aws.md`
  - `evidence/snowflake.md`
  - `evidence/mdm-hosted-graph.md`
  - `evidence/dashboard-security.md`
- **D-12:** Every unresolved launch-impacting item appears as a `BLOCKED` row in the matrix with owner/source, required fix, and required rerun proof.
- **D-13:** Evidence files include only commands that were actually run or verified. Planned commands that cannot run yet belong as blockers in the gate matrix, not evidence entries.
- **D-14:** Dashboard screenshots are optional if secret-safe. Text UAT notes are sufficient for Phase 1.
- **D-15:** Generated JSON such as `infra/aws-*-application.json` should be summarized only: file presence, schema/key checks, state machine names, and sanitized paths. Do not paste full generated JSON.

### Production Source Of Truth

- **D-16:** Live AWS/Snowflake discovery and command checks are authoritative for production readiness. Manifests and docs are supporting evidence.
- **D-17:** Missing `infra/aws-prod-application.json` is a launch blocker until live discovery or a successful production deploy provides equivalent evidence.
- **D-18:** The gate matrix must distinguish dev proof from prod proof. Dev evidence is precedent; go-live requires separate production proof.
- **D-19:** Phase 1 must require production AWS profile/account, Snowflake connection/database, deploy image refs, app summary path, MDM secret names, and Native App app/compute pool selector before execution planning.

### Preflight And Spend Boundary

- **D-20:** Local/static readiness checks, production identifiers, secret-safety scan, live discovery, and strict hosted graph preflight must pass before any paid or state-changing execution.
- **D-21:** Pure read-only status and metadata checks are allowed before all gates are green if they do not start workloads or reveal secret values.
- **D-22:** Before AWS MDM E2E starts, Phase 1 requires local `edgar-warehouse mdm verify-graph` using the target Snowflake connection/database and Native App compute pool, plus production identifiers and app summary validation.
- **D-23:** Emergency/debug runs with skipped preflight are allowed only as non-acceptance. They cannot satisfy go-live gates.
- **D-24:** Bounded production runs require explicit limits, target scope, and stop conditions before execution.

### Data Issue Routing

- **D-25:** Phase 1 needs a concrete triage table by layer. For ingestion, bronze/silver, MDM, hosted graph, dbt/gold, Native App, dashboard, and permissions, the table should include symptom, likely source, evidence to check, owner, blocker status, and next action.
- **D-26:** Operators should start with CLI verification and dbt tests, then inspect the dashboard.
- **D-27:** The dashboard is inspection only after CLI/dbt gates. It explains issues but does not define acceptance.
- **D-28:** Failed CLI/dbt/Native App gates are launch-blocking. Dashboard-only warnings block only when they point to a failed gate or launch-impacting data gap.
- **D-29:** Issue routing should use role-based owners: AWS operator, Snowflake operator, MDM operator, dashboard reviewer, and release owner.

### Agent Discretion

None. The user made explicit decisions for all selected gray areas.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Go-Live Workstream

- `.planning/workstreams/go-live/PROJECT.md` - Milestone scope, current context, and launch boundaries.
- `.planning/workstreams/go-live/REQUIREMENTS.md` - Phase 1 requirements `LIVE-01`, `SEC-01`, `ISO-01`, and `ISO-02`.
- `.planning/workstreams/go-live/ROADMAP.md` - Phase 1 goal, dependencies, and success criteria.
- `.planning/workstreams/go-live/STATE.md` - Current go-live state and known inputs.

### Project Policy

- `.planning/PROJECT.md` - Locked AWS-only, Terraform-passive, runtime-role, and storage decisions.
- `AGENTS.md` - Repo operating rules, AWS path, tooling, and secret-safety expectations.

### Deployment And Runtime Scripts

- `infra/scripts/deploy-aws-application.sh` - Active AWS deployment surface, deploy inputs, MDM deployment flags, manifest behavior, and ECR cleanup behavior.
- `infra/scripts/run-aws-mdm-e2e.sh` - Hosted graph E2E surface, local `verify-graph` preflight, `--status-only`, `--skip-preflight`, Snowflake connection/database, and Native App compute-pool selector behavior.
- `infra/scripts/deploy-snowflake-stack.sh` - Snowflake native pull/dbt/dashboard deployment wrapper and required Snowflake/dbt inputs.

### Runbooks And Existing Evidence

- `docs/runbook.md` - Existing end-to-end setup runbook; note it contains stale install/docs assumptions that Phase 1 may need to classify.
- `docs/aws-mdm-source-to-mdm.md` - MDM source readiness and silver/ADV prerequisites.
- `docs/aws-mdm-snowflake-postgres-cutover.md` - Snowflake Postgres cutover, MDM secret update, stale EDGAR identity ARN hazard, and ECR cleanup hazard.
- `examples/mdm_graph_dashboard/README.md` - Current dashboard operator docs; currently still contains external `NEO4J_*` assumptions in this worktree.
- `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md` - Dev hosted graph E2E proof and Native App verification evidence.
- `.planning/workstreams/neo4j-snowflake/phases/04-dashboard-hosted-graph-migration/04-02-SUMMARY.md` - Dashboard implementation migrated to hosted graph helper.
- `.planning/workstreams/neo4j-snowflake/phases/04-dashboard-hosted-graph-migration/04-03-PLAN.md` - Remaining dashboard docs/final verification closeout that blocks go-live evidence until completed.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `infra/scripts/deploy-aws-application.sh`: production deployment readiness should inspect explicit image refs, MDM flags, secret ARN resolution, generated app summary output, and known cleanup hazards.
- `infra/scripts/run-aws-mdm-e2e.sh`: production E2E readiness should use the same local `verify-graph` preflight that AWS later runs; `--status-only` is read-only status evidence, while `--skip-preflight` is debug-only non-acceptance.
- `infra/scripts/deploy-snowflake-stack.sh`: Snowflake readiness should use existing native-pull, validation, dbt, and dashboard upload switches instead of new deployment surfaces.
- `examples/mdm_graph_dashboard/README.md`: current docs are useful as a launch evidence target but still need hosted graph cleanup before go-live acceptance.

### Established Patterns

- AWS Terraform is passive infrastructure; application rollout happens through scripts and explicit operator actions.
- Evidence artifacts should summarize generated JSON and command results rather than embedding full logs or sensitive values.
- Dev proof is precedent only. Production proof must be captured separately and linked in the gate matrix.
- Dashboard review is read-only and secondary to CLI/dbt/Native App acceptance gates.

### Integration Points

- Phase 1 should create its artifacts under `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/`.
- The gate matrix should route to `evidence/aws.md`, `evidence/snowflake.md`, `evidence/mdm-hosted-graph.md`, and `evidence/dashboard-security.md`.
- Later Phase 2 and Phase 3 planning should consume the Phase 1 matrix to decide what is safe to run, what is blocked, and which production identifiers are required.

</code_context>

<specifics>
## Specific Ideas

- Treat absent `infra/aws-prod-application.json` as a launch blocker until live production discovery or successful production deployment provides equivalent evidence.
- Known deploy hazards must be explicitly guarded in the runbook/checklist before deploy:
  - stale `edgar-identity` secret ARN from cached manifests
  - ECR cleanup deleting an image digest that a deploy is about to use
- Planned-but-blocked commands should not be recorded in evidence files. They belong as `BLOCKED` matrix rows until actually run or verified.
- Operators investigate launch data issues by starting with CLI verification and dbt tests, then using the dashboard to inspect and explain issues.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope.

</deferred>

---

*Phase: 1-Production Readiness Inventory And Launch Gate Contract*
*Context gathered: 2026-06-13*
