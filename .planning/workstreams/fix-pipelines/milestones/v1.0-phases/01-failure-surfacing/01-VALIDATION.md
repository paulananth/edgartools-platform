---
phase: 1
phase-slug: failure-surfacing
date: 2026-05-15
---

# Phase 1: Failure Surfacing — Validation Strategy

## Test Framework

| Property | Value |
|----------|-------|
| Framework | bash + AWS CLI (no pytest) |
| Config file | N/A |
| Static check command | `sed -n '1288,1530p' infra/scripts/deploy-aws-application.sh \| grep '"ToleratedFailurePercentage"\|"MaxAttempts"'` |
| Integration test command | `bash scripts/ops/test-failure-surfacing.sh` |

## Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Command | Notes |
|--------|----------|-----------|---------|-------|
| OBS-01 | `bootstrap_phased` reaches FAILED when batch fails | Integration (live) | `bash scripts/ops/test-failure-surfacing.sh` | Requires deployed dev SM; ~22-30 min |
| OBS-01 | `BatchBootstrap` has `ToleratedFailurePercentage: 0` in definition | Static check | `sed -n '1288,1403p' infra/scripts/deploy-aws-application.sh \| grep ToleratedFailurePercentage` | Offline, fast |
| OBS-01 | `ecs_state()` in `write_bootstrap_phased_definition` has `MaxAttempts: 3` | Static check | `sed -n '1310,1340p' infra/scripts/deploy-aws-application.sh \| grep MaxAttempts` | Offline, fast |
| OBS-02 | `BatchSilver` has `ToleratedFailurePercentage: 0` | Static check | `sed -n '1476,1496p' infra/scripts/deploy-aws-application.sh \| grep ToleratedFailurePercentage` | Offline, fast |
| OBS-02 | `ecs_state()` in `write_silver_mdm_gold_definition` has `MaxAttempts: 3` | Static check | `sed -n '1431,1454p' infra/scripts/deploy-aws-application.sh \| grep MaxAttempts` | Offline, fast |
| OBS-02 | `gold-refresh`, `mdm-gold`, `ownership-mdm-gold` already hard-fail | Verification (code read) | No Distributed Map in their definitions — sequential ECS chains | Code inspection, no change needed |

## Sampling Rate

- **Per task commit:** Static grep for `"ToleratedFailurePercentage": 10` and `"MaxAttempts": 2` in lines 1288-1530 — must return zero matches
- **Phase gate:** `bash scripts/ops/test-failure-surfacing.sh` green before `/gsd-verify-work`

## Wave 0 Gaps

- [ ] `scripts/ops/test-failure-surfacing.sh` — new file covering OBS-01 live behavior; no existing infrastructure needed beyond the deployed dev state machine
