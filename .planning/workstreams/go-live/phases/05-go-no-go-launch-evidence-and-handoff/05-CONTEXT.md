# Phase 5: Go/No-Go Launch, Evidence, And Handoff - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 5 closes the v1.5 go-live milestone by assembling the final launch
decision packet, rollback/stop procedures, post-launch monitoring checklist,
and follow-up work capture. It does not run production launch — the production
gates are still BLOCKED on missing prod credentials and infrastructure. It
documents the current state honestly (NO-GO — conditional), records exactly
what is needed to flip to GO, and hands off the monitoring and incident
procedures for when that happens.

Phase 5 explicitly scopes:
1. **Go/no-go packet** (`05-GO-NO-GO-PACKET.md`) — new document in the phase
   directory synthesizing the launch gate matrix into a narrative launch
   decision (D-01).
2. **Launch ops runbook** (`runbook/launch-ops.md`) — single runbook covering
   stop and rollback procedures for all four systems: AWS Step Functions,
   Snowflake tasks/dbt, MDM runs, dashboard (D-03).
3. **Post-launch monitoring checklist** (`runbook/post-launch-monitoring.md`)
   — monitoring and incident checklist in the phase directory (D-04).
4. **TODOS.md additions** — repo-level capture of follow-up work that survives
   this milestone (D-05). Phase 5 explicitly scopes TODOS.md as a modified
   file per ISO-01 exception.

All other files are read-only references. The launch gate matrix
(`01-LAUNCH-GATE-MATRIX.md`) is NOT modified in Phase 5 — it is read for
synthesis only.

</domain>

<decisions>
## Implementation Decisions

### Go/No-Go Packet Format (D-01)
- **D-01:** Phase 5 creates a **new document** `05-GO-NO-GO-PACKET.md` in
  `.planning/workstreams/go-live/phases/05-go-no-go-launch-evidence-and-handoff/`.
  Same isolation pattern as all prior phase artifacts. The packet synthesizes
  the launch gate matrix into a readable launch decision and links back to the
  matrix for gate-level detail. It does NOT duplicate individual gate rows.

### Launch Decision Framing (D-02)
- **D-02:** The launch decision is **NO-GO — conditional**. The packet
  explicitly states the current decision is NO-GO and lists exactly what must
  be satisfied to flip to GO. Honest and operator-facing. The dev rehearsal
  work (5/5 phases, 10/10 plans complete) is cited as precedent, not as a
  substitute for prod proof.
- **D-02a:** The NO-GO reasons are: (a) prod AWS infrastructure not yet
  applied (`infra/aws-prod-application.json` absent), (b) prod MDM Secrets
  Manager secrets not yet populated, (c) prod Snowflake dbt not yet deployed,
  (d) prod hosted graph E2E not yet verified, (e) prod dashboard UAT not yet
  run. Each must flip from BLOCKED to PASS before a GO decision is possible.
- **D-02b:** The packet MUST NOT fabricate prod evidence. It cites dev
  precedent runs from Phases 2-4 with the annotation "dev precedent only —
  prod proof required separately."

### Rollback and Stop Procedure Scope (D-03)
- **D-03:** Stop and rollback procedures live in a **single runbook**
  `runbook/launch-ops.md`. It covers four systems:
  1. AWS Step Functions — stop a running execution (`aws stepfunctions
     stop-execution`); abort a distributed map; resume or rerun safely.
  2. Snowflake tasks/dbt — suspend a Snowflake task (`ALTER TASK ... SUSPEND`);
     recover from failed dynamic table refresh; rerun dbt.
  3. MDM runs — abort a Step Functions MDM E2E; MDM counts check after abort;
     safe rerun sequence.
  4. Dashboard — kill the local Streamlit process; confirm no write state was
     modified.
- **D-03a:** All commands in `launch-ops.md` are read-only checks or
  bounded-stop commands. No `put-secret-value`, no `delete`, no destructive
  S3 operations. Secret values must not appear.

### Post-Launch Monitoring Document (D-04)
- **D-04:** Post-launch monitoring checklist lives in
  `runbook/post-launch-monitoring.md` in the Phase 5 directory. ISO-01
  isolation preserved — this is a go-live planning artifact, not a permanent
  repo runbook. No changes to `infra/runbooks/` or any repo source tree.
- **D-04a:** The monitoring checklist covers exactly the OPS-02 scope: Step
  Functions status, CloudWatch logs, Snowflake task history, dbt test
  failures, MDM counts, hosted graph verification (`mdm verify-graph`),
  Native App compute pool health, dashboard availability. Each item has the
  diagnostic command, expected output shape, and escalation owner.
- **D-04b:** Diagnostic commands in the monitoring checklist are read-only.
  No mutation commands. Secret values must not appear (use secret names, not
  values).

### Future Work Capture (D-05)
- **D-05:** Follow-up items that survive this milestone are captured in
  **`TODOS.md`** (repo-level). Phase 5 explicitly scopes TODOS.md as a
  modified file. Items that are go-live-specific but useful to future
  operators also appear in a "Post-Launch Follow-Up" section of the go/no-go
  packet — not duplicating TODOS.md entries, but providing milestone-local
  context.
- **D-05a:** TODOS.md entries follow the existing repo format: title,
  **What**, **Why**, **Where** (file + line when applicable). Secret values
  must not appear.
- **D-05b:** Known follow-up items to capture (non-exhaustive — planner
  should add any surfaced during execution):
  - Production dashboard UAT (prod MDM secrets + prod Snowflake connection
    required; deferred from Phase 4 D-08/D-09).
  - Production MDM secrets population runbook execution (prod secret names
    `edgartools-prod/mdm/postgres_dsn` and `edgartools-prod/mdm/snowflake`).
  - `EDGARTOOLS_PROD_DEPLOYER` direct SELECT grants on `EDGARTOOLS_SOURCE`
    (analogous to the dev deployer gap documented in CLAUDE.md/TODOS.md).
  - Removal or formal deprecation of external Neo4j runtime remnants
    (deferred from REQUIREMENTS.md "Future Requirements").

### Secret Safety (consistent with all prior phases)
- **D-06:** No secrets, DSNs, passwords, tokens, raw connector exceptions,
  stack traces, Terraform state, or sensitive generated deployment values in
  any Phase 5 file. Secret names (e.g. `edgartools-prod/mdm/postgres_dsn`)
  are allowed; secret values are not.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 5 requirements and goal
- `.planning/workstreams/go-live/ROADMAP.md` — Phase 5 goal, success criteria
  1-5, and dependency on Phase 4.
- `.planning/workstreams/go-live/REQUIREMENTS.md` — OPS-01 and OPS-02
  full definitions and traceability table.

### Launch gate matrix (primary synthesis source for the packet)
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md`
  — 25 BLOCKED rows (prod gates) and 6 PASS rows. The go/no-go packet
  synthesizes these without duplicating individual rows. Read fully before
  writing the packet.

### Prior phase evidence (dev precedent to cite in packet)
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/` — AWS, Snowflake, MDM/hosted-graph, dashboard-security evidence templates.
- `.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md` — Phase 3 MDM secrets runbook (pattern for stop/rollback).
- `.planning/workstreams/go-live/phases/04-operator-dashboard-and-data-issue-triage/runbook/data-issue-triage.md` — Phase 4 triage guide (cross-reference in monitoring checklist).

### Runbook format precedent (mirror for Phase 5 runbooks)
- `.planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md` — deployment + stop procedure precedent.
- `.planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/dbt-gold.md` — Snowflake task/dbt runbook precedent.
- `.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md` — MDM runbook precedent.

### State and blockers
- `.planning/workstreams/go-live/STATE.md` — current blocker list (prod
  identifiers, `infra/aws-prod-application.json` absent, etc.).
- `TODOS.md` — repo-level outstanding items (Phase 5 D-05 adds entries here).

</canonical_refs>

<specifics>
## Specific Ideas

### Go/no-go packet must-haves (OPS-01 / D-01 / D-02)
The packet (`05-GO-NO-GO-PACKET.md`) must contain:
- **Current decision header**: `## Launch Decision: NO-GO — Conditional` with date
- **Dev precedent summary**: 5/5 phases complete, 10/10 plans, dev rehearsal
  evidence summary per system (cite phase + evidence file, annotate "dev
  precedent only — prod proof required separately")
- **Blocker enumeration**: exactly the 5 NO-GO reasons from D-02a, each with
  the specific launch gate matrix row(s) it blocks and the remediation step
- **Prod launch sequence**: ordered checklist of commands when all gates are
  GO (AWS deploy → Snowflake native pull → dbt → MDM secrets → MDM E2E →
  verify-graph → dashboard UAT)
- **Required approvals**: who must sign off before each phase of the sequence
- **Evidence capture rules**: what non-secret evidence must be recorded and
  where (same SEC-01 rules from Phase 1)

### Launch ops runbook must-haves (OPS-01 / D-03)
`runbook/launch-ops.md` must contain per system:
- **Stop command**: e.g. `aws stepfunctions stop-execution --execution-arn <arn>` (metadata only)
- **Verify stopped**: how to confirm execution is not still running
- **Safe resume/rerun**: conditions under which rerun is safe (idempotency notes)
- **Rollback scope**: what state is left behind after a stop (S3 files written
  so far, MDM migration applied, Snowflake task state)

### Post-launch monitoring must-haves (OPS-02 / D-04)
`runbook/post-launch-monitoring.md` must contain exactly the OPS-02 items:
- Step Functions execution status (`aws stepfunctions list-executions ...`)
- CloudWatch Logs tail for ECS tasks
- Snowflake task history (`SHOW TASKS`, `SELECT ... FROM TASK_HISTORY`)
- dbt test failures (`dbt test --target prod`)
- MDM counts (`edgar-warehouse mdm counts`)
- Hosted graph verification (`edgar-warehouse mdm verify-graph`)
- Native App compute pool health (`SHOW COMPUTE POOLS`)
- Dashboard availability (Streamlit health check URL or process status)
Each item: diagnostic command, expected output shape, threshold for escalation, owner.

### TODOS.md entry format (D-05)
Follow existing repo format:
```markdown
## <Title>

**What:** <one sentence>
**Why:** <one sentence root cause or consequence>
**Where:** <file:line or system name>
```
No secret values. Use secret name placeholders (e.g. `edgartools-prod/mdm/postgres_dsn`).

</specifics>

<deferred>
## Deferred Ideas

- Production launch execution itself — blocked by prod credentials/infra. Phase 5
  documents the path; actual prod launch is a post-milestone operation.
- Managed dashboard deployment (Streamlit-in-Snowflake) — out of scope per
  REQUIREMENTS.md "Out of Scope".
- Historical trend views for data quality and graph parity — future requirement
  post go-live per REQUIREMENTS.md.
- Cost dashboards for Native App compute pools and Step Functions — future
  requirement post go-live.
- Formal external Neo4j runtime deprecation — deferred per REQUIREMENTS.md
  "Future Requirements".

</deferred>

---

*Phase: 5-go-no-go-launch-evidence-and-handoff*
*Context gathered: 2026-06-16*
