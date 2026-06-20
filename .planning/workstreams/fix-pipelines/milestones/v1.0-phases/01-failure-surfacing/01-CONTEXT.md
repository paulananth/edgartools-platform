# Phase 1: Failure Surfacing - Context

**Gathered:** 2026-05-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Change `ToleratedFailurePercentage` from 10 to 0 on the `BatchBootstrap` and `BatchSilver`
Map states in `bootstrap_phased` and `silver_mdm_gold` respectively, increase ECS task
retries from 2 to 3, and write a scripted failure-injection test that confirms the execution
reaches FAILED when a batch fails. Also add a recovery runbook section to `docs/runbook.md`.

What this phase does NOT do: change error handling for `gold-refresh`, `mdm-gold`, or
`ownership-mdm-gold` (those are already hard-fail — no Distributed Map tolerance configured),
add failure notifications (Phase 3), or touch `status.sh` (Phase 2).

</domain>

<decisions>
## Implementation Decisions

### Tolerance threshold
- **D-01:** Set `ToleratedFailurePercentage: 0` on `BatchBootstrap` (in `bootstrap_phased`)
  and `BatchSilver` (in `silver_mdm_gold`). No intermediate check state, no env var — just 0.
- **D-02:** Increase ECS task `MaxAttempts` from 2 to 3 on all `ecs_state()` calls in both
  state machine definitions. 3 retries with exponential backoff cover transients; failure after
  3 attempts is a real problem.

### Partial success policy
- **D-03:** Recovery path is: re-run only the failed batches using `targeted_resync` after
  identifying failed child executions in the Step Functions console. A full bootstrap_phased
  re-run is also acceptable (DEC-009 idempotency ensures already-loaded CIKs are skipped).
- **D-04:** Failed-batch recovery procedure is documented as a new section in
  `docs/runbook.md` (not a new file). No automation code for this in Phase 1.

### Verification approach
- **D-05:** Verification is two-part: (1) check the generated JSON definition file has
  `ToleratedFailurePercentage: 0` after deploy; (2) run a scripted failure-injection test
  (`scripts/ops/test-failure-surfacing.sh`) that triggers `bootstrap_phased` with an invalid
  CIK (e.g. `9999999`) and polls until the execution reaches FAILED state (not SUCCEEDED).
- **D-06:** The test script lives in `scripts/ops/test-failure-surfacing.sh` — small shell
  script, repeatable, usable as a regression check. It confirms runtime behavior, not just
  the definition text.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### State machine definitions (where the fix lives)
- `infra/scripts/deploy-aws-application.sh` lines ~1288–1402 — `write_bootstrap_phased_definition()` Python-in-bash heredoc that generates the `bootstrap_phased` state machine. `BatchBootstrap` Map state with `ToleratedFailurePercentage: 10` at ~line 1350. `ecs_state()` retry config at ~line 1326.
- `infra/scripts/deploy-aws-application.sh` lines ~1410–1530 — `write_silver_mdm_gold_definition()` Python-in-bash heredoc. `BatchSilver` Map state with `ToleratedFailurePercentage: 10` at ~line 1480.

### Phase requirements
- `.planning/workstreams/fix-pipelines/REQUIREMENTS.md` — OBS-01 (bootstrap_phased), OBS-02 (all 5 machines)
- `.planning/workstreams/fix-pipelines/ROADMAP.md` Phase 1 — success criteria

### Existing ops tooling (context for the test script)
- `scripts/ops/status.sh` — existing pipeline status; use its AWS CLI patterns as reference for the test script polling loop
- `scripts/ops/diagnose-execution.sh` — existing diagnose tool; test script can call this to confirm failure details

### Project constraints
- `.planning/PROJECT.md` DEC-009 — SEC artifacts are idempotent; already-loaded CIKs are skipped on re-run
- `.planning/PROJECT.md` DEC-011 — Terraform is passive infra only; state machine changes go in deploy-aws-application.sh, not Terraform

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ecs_state()` helper (~line 1310 and ~line 1431 in deploy-aws-application.sh): shared function
  that generates ECS task state JSON. The `retry_secs` and an implied `max_attempts` parameter
  are the edit points. Currently hardcoded `"MaxAttempts": 2` inside the dict — needs to become 3.
- `scripts/ops/status.sh` AWS CLI patterns: use the Step Functions `describe-execution` poll
  loop pattern already in status.sh as the basis for the test script.

### Established Patterns
- State machine definitions are generated as Python-in-bash heredocs within
  `deploy-aws-application.sh` — changes to state machine definitions always go here, not in
  separate JSON files checked into the repo.
- `upsert_state_machine()` (~line 1532) handles create-or-update on deploy — no manual
  Step Functions console edits needed; run `deploy-aws-application.sh` to apply changes.

### Integration Points
- The fix only touches two Python-in-bash definition functions. No other files in the
  deploy script need changes.
- After deploying, the new state machine definition takes effect immediately for new
  executions — existing in-flight executions are unaffected.

</code_context>

<specifics>
## Specific Ideas

- Invalid CIK for the failure-injection test: `9999999` (does not exist in SEC EDGAR; will
  cause `bootstrap-batch` to fail to fetch submissions and exit non-zero after retries)
- The test script should poll Step Functions with `describe-execution` until status is
  FAILED or SUCCEEDED, then assert FAILED and print the failed execution ARN
- Recovery runbook section in `docs/runbook.md`: "How to re-run failed batches after a
  partial bootstrap_phased failure" — steps: identify failed child executions → extract
  CIK list → trigger `targeted_resync` with those CIKs

</specifics>

<deferred>
## Deferred Ideas

- Batch log correlation (link failed ECS task logs to specific CIK) — belongs in Phase 2
  or a future milestone (batch-logs.sh improvement)
- Automation script for failed-batch CIK extraction and targeted_resync re-trigger —
  operator runbook is sufficient for Phase 1; script can be a future enhancement

</deferred>

---

*Phase: 1-Failure Surfacing*
*Context gathered: 2026-05-15*
