---
plan: 01-01
phase: 01-failure-surfacing
status: complete
completed: 2026-05-16
requirements:
  - OBS-01
  - OBS-02
---

# Plan 01-01 Summary: Edit deploy-aws-application.sh and Redeploy State Machines

## What Was Built

Four literal value changes in `infra/scripts/deploy-aws-application.sh` across two independent Python heredoc subprocesses:

| Function | Change | Before | After |
|----------|--------|--------|-------|
| `write_bootstrap_phased_definition()` ecs_state | MaxAttempts | 2 | 3 |
| `write_bootstrap_phased_definition()` batch_map (BatchBootstrap) | ToleratedFailurePercentage | 10 | 0 |
| `write_silver_mdm_gold_definition()` ecs_state | MaxAttempts | 2 | 3 |
| `write_silver_mdm_gold_definition()` batch_map (BatchSilver) | ToleratedFailurePercentage | 10 | 0 |

Both updated state machine definitions were deployed to the dev environment via `deploy-aws-application.sh --skip-build`.

## Verification

Live AWS API confirms both deployed state machines have the new values:

```
BatchBootstrap ToleratedFailurePercentage: 0
RunBatch MaxAttempts: 3

BatchSilver ToleratedFailurePercentage: 0
RunBatch MaxAttempts: 3
```

DEC-004 invariant intact: `--artifact-policy skip` argument in `write_silver_mdm_gold_definition` was not disturbed (line 1473).

OBS-02 note: `gold-refresh`, `mdm-gold`, and `ownership-mdm-gold` use sequential ECS task states with no Distributed Map — they already hard-fail with no code changes required.

## Decisions

- No changes to the loop at line 1572 or any `write_single_workflow_definition()` calls — out of scope
- `--skip-build` used for deploy since only Step Functions definitions changed (no Docker rebuild)

## Commits

- `feat(01-01): set ToleratedFailurePercentage=0 and MaxAttempts=3 in both Distributed Map heredocs`
