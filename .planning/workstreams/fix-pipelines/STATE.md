---
workstream: fix-pipelines
milestone: v1.0 Pipeline Observability
status: planning
updated: 2026-05-15
progress:
  phases_complete: 0
  phases_total: 3
---

# Project State — fix-pipelines

## Current Position

Phase: Phase 1 — Failure Surfacing (planning)
Plan: —
Status: Roadmap defined, ready to plan Phase 1
Last activity: 2026-05-15 — Roadmap created (3 phases, 6 requirements mapped)

[░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 0% (0/3 phases complete)

## Milestone Context

**v1.0 Pipeline Observability**

Goal: Make pipeline failures impossible to miss — hard Step Functions errors, complete
status.sh coverage for all 5 state machines, and SNS email notifications on failure.

Requirements: OBS-01 through OBS-06 (see REQUIREMENTS.md)

## Phase Summary

| Phase | Goal | Requirements | Status |
|-------|------|--------------|--------|
| 1 — Failure Surfacing | Hard FAILED state on any stage error, all 5 machines | OBS-01, OBS-02 | Not started |
| 2 — Status Completeness | Complete stage display + active stage marker in status.sh | OBS-03, OBS-04 | Not started |
| 3 — Failure Notifications | SNS email on FAILED with pipeline name, ARN, stage, CW deep-link | OBS-05, OBS-06 | Not started |

## Progress

**Phases Complete:** 0/3
**Current Plan:** N/A

## Session Continuity

**Stopped At:** Roadmap creation complete
**Resume File:** None

## Accumulated Context

### Active Decisions
- SNS email chosen as notification delivery mechanism (not Slack)
- Failure surfacing covers all 5 state machines: bootstrap-phased, silver-mdm-gold,
  gold-refresh, mdm-gold, ownership-mdm-gold
- Phase 3 depends on Phase 1: notifications on a lying state machine (reaching SUCCEEDED
  despite stage errors) are worse than no notifications — Phase 1 must land first
- SNS topic, subscription, and EventBridge rule are Terraform-managed (DEC-011: Terraform
  is passive infra only — no ad-hoc script wiring for the notification path)
- Distributed Map ToleratedFailurePercentage must not silently absorb child failures
  (bootstrap-phased BatchBootstrap, silver-mdm-gold BatchSilver) — explicit success
  criterion in Phase 1

### Blockers
None

### Pending Todos
None
