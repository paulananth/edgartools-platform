---
plan: 01-02
phase: 01-failure-surfacing
status: complete
completed: 2026-05-16
requirements:
  - OBS-01
  - OBS-02
---

# Plan 01-02 Summary: Failure-Injection Test Script + Runbook Recovery Section

## What Was Built

### Task 1: scripts/ops/test-failure-surfacing.sh

New executable script that provides a repeatable failure-injection regression test for `bootstrap_phased`. It:

1. Starts a `bootstrap_phased` execution
2. Polls `get-execution-history` for `stateExitedEventDetails.name == 'SeedUniverse'` before proceeding
3. Sleeps 3 seconds (SFN scheduling lag mitigation) then overwrites `cik_batches.jsonl` with invalid CIK `9999999`
4. Polls `describe-execution` until a terminal state (30s interval, 45-min hard timeout via `MAX_WAIT_SECONDS=2700`)
5. Asserts the terminal status is `FAILED` — exits 0 on pass, exits 1 on assertion failure or timeout

Follows the exact arg-parsing and `aws_()` alias conventions of `trigger.sh` and `status.sh`.

### Task 2: docs/runbook.md recovery section

Appended `## Recovering from a partial bootstrap_phased failure` with:
- **Option A**: Full re-run (`./scripts/ops/trigger.sh bootstrap`) — cites DEC-009 idempotency as the basis for safety
- **Option B**: Targeted recovery — step-by-step commands to find the Map Run ARN, list failed child executions, extract CIK lists, and trigger `targeted_resync` per-CIK
- Note on MDM-stage failure path (`trigger.sh mdm-gold`)
- Note on post-failure child execution behavior (AWS may run children after threshold is exceeded)

## Verification

```
bash -n scripts/ops/test-failure-surfacing.sh → OK
MAX_WAIT_SECONDS=2700 → present (header comment + variable declaration)
stateExitedEventDetails → present (1 occurrence)
BRONZE_BUCKET → validated at script start (5 occurrences)
aws_() → function defined (1 occurrence)
chmod +x → executable confirmed
```

```
"Recovering from a partial bootstrap_phased failure" heading → present (1 occurrence)
aws stepfunctions list-executions with --map-run-arn → present (Step 3, multiline)
DEC-009 → referenced (2 occurrences)
trigger.sh bootstrap → present (Option A)
```

## Commits

- `feat(01-02): add failure-injection regression test for bootstrap_phased`
- `docs(01-02): append bootstrap_phased failure recovery section to runbook`
