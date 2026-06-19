# Project: EdgarTools Platform

workstream: go-live
status: active
updated: 2026-06-19

---

## Core Value

Launch the AWS-first EdgarTools Platform into production with repeatable operator gates
that prove SEC ingestion, Snowflake native pull, dbt gold, MDM, hosted graph verification,
and dashboard inspection are ready without adding non-AWS architecture or unsafe secret
handling.

---

## Current Milestone: v1.6 Production Launch Execution

**Goal:** Turn the v1.5 `NO-GO - Conditional` launch decision into `GO` by executing the
documented production sequence and capturing secret-safe PASS evidence.

**Target features:**

- Prod AWS infrastructure is applied and the active AWS application deploy is recorded with
  non-secret evidence.
- Prod MDM Secrets Manager values are populated for the two required production secrets,
  then MDM connectivity, migration, and counts pass.
- Snowflake native pull is deployed for production, and `dbt run --target prod` plus
  `dbt test --target prod` pass with freshness evidence.
- Prod hosted graph E2E passes through bounded `mdm sync-graph`, strict
  `mdm verify-graph`, and AWS MDM E2E execution.
- Dashboard reviewer completes production or production-like read-only UAT for all 5
  launch-critical views.
- Release owner flips the go/no-go packet only after all five blockers report PASS.

**Success metric:** the five blocker themes in
`phases/05-go-no-go-launch-evidence-and-handoff/05-GO-NO-GO-PACKET.md` move from
NO-GO to PASS with owner sign-off, ordered execution, and evidence that preserves the
v1.5 secret-safety contract.

---

## Current State

**Shipped:** v1.5 Go Live (2026-06-19) — see [`milestones/v1.5-ROADMAP.md`](milestones/v1.5-ROADMAP.md) and [`milestones/v1.5-REQUIREMENTS.md`](milestones/v1.5-REQUIREMENTS.md).

v1.5 delivered a complete, secret-safe, independently-verified launch-readiness evidence
bundle and operator handoff across 5 phases / 12 plans: launch gate matrix and blocker
inventory (Phase 1), AWS/Snowflake production deployment dry run (Phase 2), MDM and hosted
graph dev rehearsal (Phase 3), operator dashboard and data-issue triage (Phase 4), and the
final go/no-go decision packet plus stop/rollback and post-launch monitoring runbooks
(Phase 5).

**Current production launch decision: NO-GO — Conditional.** Production launch is blocked
on exactly 5 documented items, each with a named owner and remediation step in
`phases/05-go-no-go-launch-evidence-and-handoff/05-GO-NO-GO-PACKET.md`:

1. Prod AWS infrastructure not yet applied.
2. Prod MDM Secrets Manager secrets not yet populated.
3. Prod Snowflake dbt not yet deployed.
4. Prod hosted graph E2E not yet verified.
5. Prod dashboard UAT not yet run.

No part of v1.5's output authorizes a production deploy, a production data load, or any
write action against production AWS, Snowflake, or MDM systems. Flipping NO-GO to GO is
itself the next milestone's work, not a continuation of v1.5 planning.

---

## Active Milestone Goals

Scope for v1.6 (execute the actual production launch sequence documented in
`05-GO-NO-GO-PACKET.md`):

- AWS operator applies the prod Terraform stack and runs the production deploy script.
- MDM operator populates the two production secrets and re-verifies connectivity/migration/counts.
- Snowflake operator deploys the native-pull stack and runs `dbt run --target prod` / `dbt test --target prod`.
- MDM operator runs the production `mdm sync-graph` → strict `mdm verify-graph` → AWS MDM E2E sequence.
- Dashboard reviewer runs UAT against a production-like read-only configuration for all 5 launch-critical views.
- Release owner flips the go/no-go decision once all 5 blockers report PASS.

Also carried forward from v1.5's Future Requirements (re-scope as needed):

- Managed dashboard deployment after local/operator dashboard launch is proven.
- Historical trend views for data quality, graph parity, and launch gate outcomes.
- Production cost dashboards for Snowflake Native App compute pools and AWS Step Functions runs.
- Removal or formal deprecation of external Neo4j runtime remnants after production hosted graph validation is stable.

The milestone remains AWS/Snowflake-focused and does not authorize out-of-order
production writes. Each production action must follow the existing runbooks, owner
approvals, and evidence-capture rules.

---

<details>
<summary>v1.5 Go Live — original milestone definition (archived 2026-06-19)</summary>

## Current Milestone: v1.5 Go Live

**Goal:** Prepare the platform for production go-live by closing launch gates across AWS
deployment, Snowflake native pull and gold, MDM Snowflake Postgres, Snowflake-hosted
Neo4j Graph Analytics verification, dashboard readiness, secrets, runbooks, and operator
validation.

**Target features:**

- A production readiness checklist covering AWS ECS/Step Functions, S3 roots, Snowflake
  native pull, dbt gold, MDM Snowflake Postgres, hosted graph verification, and dashboard
  inspection.
- A cutover runbook for deploying and validating production through existing AWS and
  Snowflake scripts.
- Acceptance gates for full E2E runs, strict `edgar-warehouse mdm verify-graph`, dbt
  tests, dashboard UAT, and secret-safe diagnostics.
- A one-stop data issue workflow that lets operators classify ingestion, silver, MDM,
  graph, dbt/gold, Native App, and dashboard issues.
- A go/no-go evidence bundle with commands run, non-secret output summaries, blockers,
  rollback or stop procedures, and post-launch monitoring checks.

Developer-facing success metric: an operator can follow the go-live runbook from a clean
production environment, prove the AWS/Snowflake/MDM/hosted graph/dashboard gates, and make
a go/no-go call with evidence that is complete, repeatable, and secret-safe.

### Current Context (as of milestone start)

- AWS remains the only active deployment path.
- Terraform remains passive infrastructure only: no runnable ECS task definitions, Step
  Functions state machines, schedules, workload commands, image rollouts, or secret values.
- Dev hosted graph E2E has succeeded through Snowflake-hosted `mdm_verify_graph`; go-live
  needs production readiness and evidence, not a new graph architecture.
- The dashboard has passed local UAT for foundation and read-only MDM connectivity; go-live
  needs production-oriented operator validation and data issue routing.
- The root `.planning` state is multi-workstream. This milestone is isolated under
  `.planning/workstreams/go-live/` and must not overwrite existing workstream artifacts.

</details>

---

## Scope Boundaries

- Keep all work AWS/Snowflake-focused. Do not add non-AWS registries, storage targets,
  workflow engines, deployment paths, or secret-management systems.
- Do not place live secret values, DSNs, tokens, passwords, Terraform state, or generated
  application JSON with sensitive values in planning artifacts.
- Do not make Terraform own runtime secrets, active workload commands, schedules, or
  deploy-time image rollouts.
- Use existing deployment and verification surfaces before adding automation.
- Dashboard work remains read-only. It must not run sync, repair, migration, grants,
  activation, deployment, or write controls.
- Existing `neo4j-pipe`, `neo4j-snowflake`, `mdm-neo4j-dashboard`, and Claude workstreams
  are protected unless a phase explicitly scopes a reviewed integration change.

---

## Relevant Architecture

```text
SEC EDGAR API
  -> edgar-warehouse CLI on AWS ECS
  -> S3 bronze and warehouse storage
  -> Snowflake native S3 pull
  -> dbt gold dynamic tables and status view
  -> MDM Snowflake Postgres
  -> Snowflake graph-ready node and edge tables
  -> Neo4j Graph Analytics Native App in Snowflake
  -> Streamlit operator dashboard
```

---

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**

1. Requirements invalidated? Move to Out of Scope with reason.
2. Requirements validated? Move to complete with phase reference.
3. New launch blockers emerged? Add them to Current Context or Pending Todos.
4. Decisions to log? Add to the relevant phase summary and update requirements if needed.
5. Runbook commands still match the repo? Update before the next phase executes.

**After this milestone:**

1. Archive go-live evidence into the release handoff. — Done: `milestones/v1.5-ROADMAP.md`, `milestones/v1.5-REQUIREMENTS.md`.
2. Promote stable operator commands into permanent docs. — Pending next milestone.
3. Decide whether remaining local-only dashboard workflows need managed deployment. — Carried to Future Requirements.
4. Capture production follow-up items as future milestones rather than expanding launch scope. — Done: `TODOS.md` D-05b entries.
