---
phase: 02-status-completeness
reviewed: 2026-05-16T00:00:00Z
depth: standard
files_reviewed: 1
files_reviewed_list:
  - scripts/ops/status.sh
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-05-16
**Depth:** standard
**Files Reviewed:** 1
**Status:** issues_found

## Summary

`scripts/ops/status.sh` is a diagnostic/observability tool that renders Step Functions execution state and ECS task status. The Phase 2 changes introduce: a MACHINES-array maintenance comment (line 35), a retry-state known-limitation comment (line 127), set arithmetic to compute `active = entered - exited - failed` (line 130), an invariant assert on that set (line 131), and a rendering-loop fix to use `active` instead of `entered` (line 135).

The rendering-loop fix (line 135) is correct and closes the core bug. The `active` set arithmetic is sound. However, the assert introduces a failure mode that is worse than the bug it guards against, and the failure-type filter it depends on (`MapStateFailed`) does not match the actual event type emitted by the Distributed Map state machines deployed in this project.

---

## Warnings

### WR-01: Assert on `active` set aborts the entire status script when invariant fires

**File:** `scripts/ops/status.sh:131`

**Issue:** Line 131 asserts `len(active) <= 1`. When this assertion fires, the embedded Python process exits with a non-zero code. Because `set -euo pipefail` is active (line 9), the pipe at line 117 propagates that exit status, causing `show_machine` to abort via `set -e`. Since `show_machine` is called inside a for-loop (line 254), the entire script exits — `show_ecs_tasks` never runs, later pipelines are never checked, and the FAILURES-DETECTED hint at the bottom is suppressed.

This is the opposite of what a status tool should do: the invariant is most likely to fire precisely in the failure scenarios (races, retries, unexpected state machine shapes) when the operator needs to see the full picture most urgently. A diagnostic abort that hides other pipeline states is strictly worse than silently rendering an ambiguous `▶` on two stages.

The comment on line 127 acknowledges that TaskFailed is an intermediate transient condition. The same transient window can cause `active` to momentarily contain two entries if StateEntered for stage N+1 is emitted before StateExited for stage N arrives in the paginated event history — Step Functions does not guarantee strict ordering across pagination boundaries.

**Fix:** Replace the assert with a stderr warning and a graceful degrade. Pick the last-entered active stage as the displayed active one, or display all active stages as `▶`:

```python
active = entered - exited - failed
if len(active) > 1:
    print(f'  warning: multiple active stages {active}', file=sys.stderr)
    # degrade gracefully — show all active; do not abort
```

Remove `assert len(active) <= 1, ...` entirely from the status tool. Asserts are appropriate in unit tests, not in observability scripts.

---

### WR-02: `MapStateFailed` does not match Distributed Map failure events — stuck-▶ rendering for BatchBootstrap and BatchSilver

**File:** `scripts/ops/status.sh:128`

**Issue:** The failure-detection block is:

```python
if e['type'] in ('TaskFailed', 'MapStateFailed', 'ExecutionFailed'):
    for n in list(entered - exited): failed.add(n)
```

All three `Map` states in this project (`BatchBootstrap` in `bootstrap-phased`, `BatchBootstrap` in `bootstrap_phased`, and `BatchSilver` in `silver-mdm-gold`) use `Mode: DISTRIBUTED` (confirmed in `infra/scripts/deploy-aws-application.sh` lines 1269, 1360, and the ownership pipeline equivalent). Distributed Map emits `MapRunFailed`, not `MapStateFailed`. `MapStateFailed` is the event type for the older inline (non-distributed) Map.

When a Distributed Map batch fails, no `MapStateFailed` event is emitted. The map stage stays in `entered` but never enters `exited`. With the Phase 2 rendering fix (`elif stage in active`), the stage will render as `▶` (running) indefinitely, even after the execution has failed. The operator sees a permanently-running BatchBootstrap, which is exactly the kind of misleading display the phase aimed to eliminate.

**Verified:** `aws stepfunctions get-execution-history` for a failed distributed map emits events of type `MapRunStarted` (line 145 already looks for this) and `MapRunFailed` when the map run fails. The parent state machine then emits `ExecutionFailed` — but only after the map-run failure propagates, which may leave a window where `active` looks non-empty but the map stage is already dead.

**Fix:** Add `MapRunFailed` to the failure-detection tuple:

```python
if e['type'] in ('TaskFailed', 'MapRunFailed', 'MapStateFailed', 'ExecutionFailed'):
    for n in list(entered - exited): failed.add(n)
```

---

### WR-03: Unquoted `$task_arns` passed to `--tasks` risks word-splitting on ARNs containing spaces or special characters

**File:** `scripts/ops/status.sh:212`

**Issue:**

```bash
aws_ ecs describe-tasks \
  --cluster "$CLUSTER" \
  --tasks $task_arns \
```

`$task_arns` is intentionally unquoted so word-splitting expands space-separated ARNs into individual arguments for `--tasks`. This works correctly in the normal case. However, if any ARN contains a space or shell glob character (unlikely but not impossible with unusual task names or future changes to how `task_arns` is constructed at line 205), word-splitting will silently corrupt the argument list rather than failing loudly.

More concretely: the `python3 -c` block at line 205 joins ARNs with `' '.join(arns)` — if `arns` is ever a list of objects rather than strings (e.g., on an unexpected AWS API shape change), the join produces `str()` representations containing brackets and commas, which then feed into shell word-splitting in unexpected ways.

**Fix:** Use a Bash array for safe multi-argument expansion:

```bash
read -ra task_arn_array <<< "$task_arns"
aws_ ecs describe-tasks \
  --cluster "$CLUSTER" \
  --tasks "${task_arn_array[@]}" \
```

---

## Info

### IN-01: Inconsistent unicode encoding — literal characters vs chr() calls in the same script

**File:** `scripts/ops/status.sh:92` and `133-136`

**Issue:** Line 92 uses literal Unicode characters (`▶✓✗⊘⏱`) in an f-string, while lines 133-136 use `chr(10003)`, `chr(10007)`, `chr(9654)`, `chr(183)` for the same (or equivalent) characters. Both approaches work, but the inconsistency makes it harder to audit what icons are actually being displayed and to maintain visual parity between the two sections.

**Fix:** Pick one style and apply it consistently. Literal characters are more readable:

```python
# lines 133-136
if   stage in exited:  icon = '✓'
elif stage in failed:  icon = '✗'
elif stage in active:  icon = '▶'
else:                  icon = '·'
```

---

### IN-02: Bare `except:` clauses catch `SystemExit` and `KeyboardInterrupt`

**File:** `scripts/ops/status.sh:78`, `186`, `275`

**Issue:** Three bare `except:` clauses swallow all exceptions, including `SystemExit` and `KeyboardInterrupt`. Standard Python practice is `except Exception:` as the minimum-width catch-all that does not intercept interpreter signals. In a diagnostic script this is low risk but degrades debuggability — a Ctrl-C during a hung AWS call will appear to silently succeed at a timestamp parse.

**Fix:** Replace bare `except:` with `except Exception:` at all three sites.

---

### IN-03: Maintenance comment on MACHINES array points to a specific function name that may drift

**File:** `scripts/ops/status.sh:35`

**Issue:** The comment reads:

```
# Stage order must match write_bootstrap_phased_definition(), write_silver_mdm_gold_definition(), etc. in infra/scripts/deploy-aws-application.sh
```

Function names in `deploy-aws-application.sh` can be renamed without updating this comment, leaving a stale reference. The comment is useful intent documentation, but pointing to function names rather than state machine names or a search pattern makes it brittle.

**Fix:** Reference the state machine name (which appears in both the deployed ARN and the deploy script) rather than the internal Python function name:

```
# Stage order must match the "States" keys in the corresponding state machine
# definitions in infra/scripts/deploy-aws-application.sh
# (search for "bootstrap-phased", "silver-mdm-gold", etc.)
```

---

_Reviewed: 2026-05-16_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
