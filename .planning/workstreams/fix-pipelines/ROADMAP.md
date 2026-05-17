# Roadmap: fix-pipelines — v1.0 Pipeline Observability

workstream: fix-pipelines
milestone: v1.0 Pipeline Observability
created: 2026-05-15
granularity: standard

---

## Milestone Goal

Make pipeline failures impossible to miss — every stage failure surfaces as a hard Step
Functions error, a single status view covers all pipelines completely, and operators get
an SNS email notification when anything fails.

---

## Phases

- [ ] **Phase 1: Failure Surfacing** - Every stage failure in all 5 state machines reaches FAILED state — executions never succeed silently when a stage errored
- [ ] **Phase 2: Status Completeness** - `status.sh` shows a complete, accurate stage-level breakdown including the actively executing stage for all 5 registered state machines
- [x] **Phase 3: Failure Notifications** - Operators receive an SNS email with full context (pipeline name, execution ARN, failed stage, CloudWatch deep-link) when any pipeline fails
- [x] **Phase 4: SEC Rate Limiting** - Enforce minimum 2 and maximum 5 concurrent calls to the SEC website across all pipeline tasks

---

## Phase Details

### Phase 1: Failure Surfacing
**Goal**: Every stage failure in all 5 state machines propagates to a hard FAILED execution — the execution status never shows SUCCEEDED when a stage errored or produced partial output
**Depends on**: Nothing (first phase)
**Requirements**: OBS-01, OBS-02
**Success Criteria** (what must be TRUE):
  1. When a stage within `bootstrap_phased` errors, the execution status in Step Functions console is FAILED (not SUCCEEDED or RUNNING)
  2. A failed child execution within a Distributed Map state (BatchBootstrap in `bootstrap_phased`, BatchSilver in `silver_mdm_gold`) propagates to the parent execution reaching FAILED — the `ToleratedFailurePercentage` does not absorb the failure silently
  3. All 5 named state machines — `bootstrap-phased`, `silver-mdm-gold`, `gold-refresh`, `mdm-gold`, `ownership-mdm-gold` — exhibit the same hard-fail behavior when any of their stages errors
  4. Running `./scripts/ops/status.sh` after a failed execution shows FAILED status (not SUCCEEDED) for the affected pipeline
**Plans**: 3 plans
Plans:
- [x] 01-01-PLAN.md — Edit deploy-aws-application.sh (4 value changes) and redeploy both state machines
- [x] 01-02-PLAN.md — Create test-failure-surfacing.sh and append runbook recovery section
- [x] 01-03-PLAN.md — Run live failure-injection test and record FAILED execution ARN

### Phase 2: Status Completeness
**Goal**: `status.sh` displays a complete, accurate stage-level breakdown for all 5 registered state machines, with clear indication of which stage is actively executing during a running pipeline
**Depends on**: Phase 1
**Requirements**: OBS-03, OBS-04
**Success Criteria** (what must be TRUE):
  1. `./scripts/ops/status.sh` displays stage-level breakdown for all 5 state machines: `bootstrap-phased`, `silver-mdm-gold`, `gold-refresh`, `mdm-gold`, and `ownership-mdm-gold` — no registered state machine is silently omitted
  2. All stage names listed for each state machine appear in the output (no stages are missing from the hardcoded stage list relative to what the state machine actually executes)
  3. For a running pipeline, exactly one stage shows the active-execution marker (`▶`) and it matches the stage currently executing in Step Functions — not just a top-level "RUNNING" with no stage detail
**Plans**: 1 plan
Plans:
- [x] 02-01-PLAN.md — Apply D-02/D-05/D-06 edits to status.sh and verify stage list correctness

### Phase 3: Failure Notifications
**Goal**: Operators are automatically notified by SNS email when any pipeline execution reaches FAILED state, with enough detail to immediately identify and locate the failure
**Depends on**: Phase 1
**Requirements**: OBS-05, OBS-06
**Success Criteria** (what must be TRUE):
  1. When any of the 5 state machines reaches FAILED state, an SNS email notification is delivered to the configured subscriber within 2 minutes of the failure
  2. The notification email body contains: pipeline name, execution ARN, failed stage name, and a direct CloudWatch Logs URL to the log stream of the failing ECS task
  3. The subscriber email address is configurable via a Terraform variable (not hardcoded) — changing the recipient requires only a `terraform apply`, not a code change
  4. The SNS topic, subscription, and failure-detection wiring (EventBridge rule on Step Functions state change) are all Terraform-managed infrastructure, consistent with DEC-011
**Plans**: 1 plan
Plans:
- [ ] 03-01-PLAN.md — Create pipeline_notifications Terraform module, wire into accounts/prod, deploy and verify

### Phase 4: SEC Rate Limiting
**Goal**: All pipeline ECS tasks enforce a minimum of 2 and a maximum of 5 concurrent outbound connections to the SEC EDGAR website — preventing rate-limit blocks and ensuring predictable throughput
**Depends on**: Nothing (independent; can land alongside Phase 2 or 3)
**Requirements**: SEC-RL-01, SEC-RL-02
**Success Criteria** (what must be TRUE):
  1. Every call to `download_sec_bytes()` in `sec_client.py` is throttled by a 9 req/sec in-process rate limiter before the retry loop — the limiter is a module-level singleton initialized at import time
  2. `CLAUDE.md` documents `BOOTSTRAP_BATCH_CONCURRENCY` recommended range as 2–5 concurrent ECS tasks, with the current default of 3 explicitly noted as compliant
  3. All existing `tests/unit/test_sec_client.py` tests pass; a new unit test confirms `try_acquire` is called exactly once per logical `download_sec_bytes()` invocation regardless of retry count
  4. `deploy-aws-application.sh` line 139 (`BOOTSTRAP_BATCH_CONCURRENCY=3`) is unchanged — value was already within compliant range per user decision
**Plans**: 1 plan
Plans:
- [ ] 04-01-PLAN.md — Add pyrate-limiter rate limiting to sec_client.py and document safe concurrency range in CLAUDE.md

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Failure Surfacing | 3/3 | Complete | 2026-05-16 |
| 2. Status Completeness | 1/1 | Complete | 2026-05-16 |
| 3. Failure Notifications | 1/1 | Complete | 2026-05-16 |
| 4. SEC Rate Limiting | 1/1 | Complete | 2026-05-16 |

---

## Coverage

| Requirement | Phase | Status |
|-------------|-------|--------|
| OBS-01 | Phase 1 | Pending |
| OBS-02 | Phase 1 | Pending |
| OBS-03 | Phase 2 | Pending |
| OBS-04 | Phase 2 | Pending |
| OBS-05 | Phase 3 | Pending |
| OBS-06 | Phase 3 | Pending |
| SEC-RL-01 | Phase 4 | Pending |
| SEC-RL-02 | Phase 4 | Pending |

All 8 requirements mapped. No orphans.
