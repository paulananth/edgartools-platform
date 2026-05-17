---
phase: 02-status-completeness
plan: "01"
subsystem: ops-scripts
tags: [status, observability, invariant, annotation]
dependency_graph:
  requires: []
  provides: [OBS-03, OBS-04]
  affects: [scripts/ops/status.sh]
tech_stack:
  added: []
  patterns: [python-assert-in-bash-heredoc, active-set-derivation]
key_files:
  created: []
  modified:
    - scripts/ops/status.sh
decisions:
  - "Use single-quoted f-string in bash double-quoted python3 -c block to avoid premature string termination"
  - "active = entered - exited - failed derived set used in both assert and rendering loop for self-documenting symmetry"
metrics:
  duration: "15 minutes"
  completed: "2026-05-16"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 1
---

# Phase 02 Plan 01: Status Completeness Targeted Edits Summary

Three targeted edits to scripts/ops/status.sh add the D-02 maintenance comment, D-05 one-▶ assert with active set, and D-06 retry-state annotation — making stage display invariants structurally explicit.

## What Changed

**File modified:** `scripts/ops/status.sh` (8 insertions, 4 deletions)

### D-02: Maintenance comment (line 35)

Added a comment immediately below the `# Format:` line and above `declare -a MACHINES=(` to document that stage order must match the `write_*_definition()` functions in `infra/scripts/deploy-aws-application.sh`.

### D-05: One-▶ assert + active set + rendering loop update (lines 130–136)

After the event-processing loop, introduced:
- `active = entered - exited - failed` — derived set of currently-executing stages
- `assert len(active) <= 1, f'one-▶ invariant violation: {active}'` — structurally enforces that at most one stage shows ▶ at any time

Updated the rendering loop's `elif` branch from `stage in entered` to `stage in active`, making the rendering loop self-documenting and consistent with the assert above.

### D-06: Retry-state known-limitation comment (line 127)

Added a comment above the `if e['type'] in ('TaskFailed',...)` line documenting that TaskFailed is an intermediate event — a stage may briefly show ✗ before a retry completes.

## Verification Results

### Task 1 — Acceptance Criteria

All checks pass:

```
D-02: grep -n 'Stage order must match write_bootstrap_phased_definition' scripts/ops/status.sh
35:# Stage order must match write_bootstrap_phased_definition(), write_silver_mdm_gold_definition(), etc. in infra/scripts/deploy-aws-application.sh

D-05: grep -n 'active = entered - exited - failed' scripts/ops/status.sh
130:active = entered - exited - failed

D-05: grep -n 'assert len(active) <= 1' scripts/ops/status.sh
131:assert len(active) <= 1, f'one-▶ invariant violation: {active}'

D-05: grep -n 'elif stage in active' scripts/ops/status.sh
135:    elif stage in active: icon = chr(9654)

D-05: grep -c 'elif stage in entered' scripts/ops/status.sh
0  (old form removed)

D-06: grep -n 'TaskFailed is intermediate' scripts/ops/status.sh
127:    # TaskFailed is intermediate — stage may show ✗ briefly before retry completes

D-05 placement: assert_pos (char 4921) > event_loop_end (char 4839) and < for_stage_pos (char 4985)
Result: OK

bash -n scripts/ops/status.sh
Result: OK (no syntax errors)
```

### Task 2 — Stage List Verification

Script output:
```
All 5 state machines verified: stage lists match deploy definitions.
```

All 5 state machines in the MACHINES array have correct stage name lists matching the deployed state machine definitions in `infra/scripts/deploy-aws-application.sh`. No discrepancies found.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Used single-quoted f-string in assert to avoid bash heredoc breakage**

- **Found during:** Task 1, Edit 2
- **Issue:** The plan specified `f"one-▶ invariant violation: {active}"` (double-quoted f-string) inside a `python3 -c "..."` block. Double quotes inside a bash double-quoted string prematurely close the string, which would cause `bash -n` to fail.
- **Fix:** Changed to `f'one-▶ invariant violation: {active}'` (single-quoted f-string). The acceptance grep `grep -n 'assert len(active) <= 1'` still matches. All existing Python strings in the block already use single quotes for the same reason.
- **Files modified:** scripts/ops/status.sh
- **Commit:** 00da5f6

## Known Stubs

None — the plan's goal is fully achieved. No placeholder data flows to UI rendering.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced.

## Self-Check: PASSED

- [x] scripts/ops/status.sh exists and contains all 3 targeted edits
- [x] Commit 00da5f6 exists: feat(02-01): add maintenance comment, one-▶ assert, and retry annotation to status.sh
- [x] bash -n scripts/ops/status.sh exits 0
- [x] Stage verification script exits 0 (All 5 state machines verified)
