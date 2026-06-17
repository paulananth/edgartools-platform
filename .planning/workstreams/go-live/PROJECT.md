# Project: EdgarTools Platform

workstream: go-live
status: active
milestone: v1.5 Go Live
updated: 2026-06-14

---

## Core Value

Launch the AWS-first EdgarTools Platform into production with repeatable operator gates
that prove SEC ingestion, Snowflake native pull, dbt gold, MDM, hosted graph verification,
and dashboard inspection are ready without adding non-AWS architecture or unsafe secret
handling.

---

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

---

## Current Context

- AWS remains the only active deployment path.
- Terraform remains passive infrastructure only: no runnable ECS task definitions, Step
  Functions state machines, schedules, workload commands, image rollouts, or secret values.
- Dev hosted graph E2E has succeeded through Snowflake-hosted `mdm_verify_graph`; go-live
  needs production readiness and evidence, not a new graph architecture.
- The dashboard has passed local UAT for foundation and read-only MDM connectivity; go-live
  needs production-oriented operator validation and data issue routing.
- Phase 1 is complete: the go-live workstream now has a launch gate matrix, secret-safe
  evidence templates, production identifier checklist, and data issue triage table under
  `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/`.
- The root `.planning` state is multi-workstream. This milestone is isolated under
  `.planning/workstreams/go-live/` and must not overwrite existing workstream artifacts.

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

1. Archive go-live evidence into the release handoff.
2. Promote stable operator commands into permanent docs.
3. Decide whether remaining local-only dashboard workflows need managed deployment.
4. Capture production follow-up items as future milestones rather than expanding launch scope.
