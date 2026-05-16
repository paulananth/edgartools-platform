# Requirements: fix-pipelines — v1.0 Pipeline Observability

workstream: fix-pipelines
milestone: v1.0 Pipeline Observability
updated: 2026-05-16

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

### SEC Rate Limiting

- [ ] **SEC-RL-01**: All direct SEC EDGAR HTTP calls made through `download_sec_bytes()` in
  `edgar_warehouse/infrastructure/sec_client.py` are subject to an in-process rate limiter
  of 9 requests/second — matching the `edgartools` library's own per-process limit
- [ ] **SEC-RL-02**: The recommended `BOOTSTRAP_BATCH_CONCURRENCY` range (2–5 concurrent ECS
  tasks) is documented in `CLAUDE.md`, with the current default of 3 noted as compliant;
  values below 2 are explicitly flagged as too low for production throughput

---

## Out of Scope (this milestone)

- Batch log correlation improvements (batch-logs.sh CIK-to-task mapping) — deferred
- `--artifact-policy skip` enforcement — covered by main roadmap Phase 4
- `GOLD_AFFECTING_COMMANDS` invariant tests — covered by main roadmap Phase 4
- Slack/PagerDuty notifications — SNS email is sufficient for v1.0
- Hard validation rejecting `BOOTSTRAP_BATCH_CONCURRENCY` outside [2, 5] at deploy time — documentation-only (per D-05)
- Cross-task coordinated rate limiting (e.g., DynamoDB token bucket) — out of scope for current scale

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
| SEC-RL-01 | Phase 4 | Pending |
| SEC-RL-02 | Phase 4 | Pending |
