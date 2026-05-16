# Requirements: fix-pipelines — v1.0 Pipeline Observability

workstream: fix-pipelines
milestone: v1.0 Pipeline Observability
updated: 2026-05-15

---

## Milestone Goal

Make pipeline failures impossible to miss — every stage failure surfaces as a hard Step
Functions error, a single status view covers all pipelines completely, and operators get
an SNS email notification when anything fails.

---

## Active Requirements

### Failure Surfacing

- [ ] **OBS-01**: Any stage failure within `bootstrap_phased` causes the execution to reach
  FAILED state — the execution must never reach SUCCEEDED when a stage errored or produced
  partial output
- [ ] **OBS-02**: The same hard-fail behavior applies to all sibling state machines:
  `silver-mdm-gold`, `gold-refresh`, `mdm-gold`, `ownership-mdm-gold`

### Status Completeness

- [ ] **OBS-03**: `status.sh` shows a complete stage-level breakdown for all 5 registered
  state machines — no stages are silently missing from the display
- [ ] **OBS-04**: `status.sh` shows which stage is actively executing during a running
  pipeline — not just "RUNNING" at the top level

### Failure Notifications

- [ ] **OBS-05**: When any pipeline execution reaches FAILED state, an SNS email notification
  is sent to a configured subscriber (email address configurable via environment variable or
  Terraform variable)
- [ ] **OBS-06**: The SNS notification body identifies: pipeline name, execution ARN, failed
  stage name, and a CloudWatch Logs deep-link for the failing ECS task

---

## Out of Scope (this milestone)

- Batch log correlation improvements (batch-logs.sh CIK-to-task mapping) — deferred
- `--artifact-policy skip` enforcement — covered by main roadmap Phase 4
- `GOLD_AFFECTING_COMMANDS` invariant tests — covered by main roadmap Phase 4
- Slack/PagerDuty notifications — SNS email is sufficient for v1.0

---

## Traceability

| REQ-ID | Phase | Status |
|--------|-------|--------|
| OBS-01 | Phase 1 | Pending |
| OBS-02 | Phase 1 | Pending |
| OBS-03 | Phase 2 | Pending |
| OBS-04 | Phase 2 | Pending |
| OBS-05 | Phase 3 | Pending |
| OBS-06 | Phase 3 | Pending |
