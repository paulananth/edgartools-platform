# Phase 2: Status Completeness - Pattern Map

**Mapped:** 2026-05-16
**Files analyzed:** 1 (one file modified, no new files created)
**Analogs found:** 2 / 1 (primary analog is the file itself; sibling analog is diagnose-execution.sh)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `scripts/ops/status.sh` | operator script / utility | request-response (AWS API polling) | `scripts/ops/status.sh` (self — existing blocks) | self |
| `scripts/ops/status.sh` (stage-progress block) | utility / in-process Python | event-driven (Step Functions history) | `scripts/ops/diagnose-execution.sh` lines 115-134 | exact role + data flow |

---

## Pattern Assignments

### `scripts/ops/status.sh` — Three targeted edit sites

This phase makes three small, localized edits. No new files are created.

---

#### Edit site 1: D-02 maintenance comment above MACHINES array

**Location:** `scripts/ops/status.sh`, above line 35

**Current code** (lines 33-41):
```bash
# ── State machines to show ────────────────────────────────────────────────────
# Format: "short-name|display-label|sm-suffix|stages..."
declare -a MACHINES=(
  "bootstrap|BOOTSTRAP-PHASED|bootstrap-phased|SeedUniverse BatchBootstrap MdmRun MdmBackfill MdmSync MdmVerify GoldRefresh"
  "silver|SILVER-MDM-GOLD|silver-mdm-gold|SeedSilverBatches BatchSilver MdmRun MdmBackfill MdmSync MdmVerify GoldRefresh"
  "gold|GOLD-REFRESH|gold-refresh|GoldRefresh"
  "mdm-gold|MDM-GOLD|mdm-gold|MdmRun MdmBackfill MdmSync MdmVerify GoldRefresh"
  "ownership|OWNERSHIP-MDM-GOLD|ownership-mdm-gold|ParseOwnershipBronze MdmRun MdmBackfill MdmSync MdmVerify GoldRefresh"
)
```

**Stage name verification (static — no live run needed):**
Cross-referenced against `infra/scripts/deploy-aws-application.sh`:
- `bootstrap-phased` States dict (line 1392-1400): `SeedUniverse`, `BatchBootstrap`, `MdmRun`, `MdmBackfill`, `MdmSync`, `MdmVerify`, `GoldRefresh` — MATCH
- `silver-mdm-gold` States dict (line 1517-1526): `SeedSilverBatches`, `BatchSilver`, `MdmRun`, `MdmBackfill`, `MdmSync`, `MdmVerify`, `GoldRefresh` — MATCH
- `gold-refresh` — single state `GoldRefresh` (implied by gold-refresh function) — MATCH
- `mdm-gold` States dict (line 1651-1657): `MdmRun`, `MdmBackfill`, `MdmSync`, `MdmVerify`, `GoldRefresh` — MATCH
- `ownership-mdm-gold` States dict (line 1714-1723): `ParseOwnershipBronze`, `MdmRun`, `MdmBackfill`, `MdmSync`, `MdmVerify`, `GoldRefresh` — MATCH

**Pattern to apply (D-02):** Add the comment line immediately above `declare -a MACHINES=(`:

```bash
# Stage order must match write_bootstrap_phased_definition(), write_silver_mdm_gold_definition(), etc. in infra/scripts/deploy-aws-application.sh
```

**Comment placement rule (established in this codebase):** Section separator comments use `# ──` with em-dash padding (see line 33 in status.sh and line 189). The new maintenance comment sits between the existing format comment (line 34) and the `declare -a MACHINES=(` line — it is a plain `#` comment, not a separator.

---

#### Edit site 2: D-05 one-▶ assert in the stage-progress Python block

**Location:** `scripts/ops/status.sh`, lines 116-134 — the `STAGE PROGRESS` embedded Python block

**Exact current code** (lines 116-134):
```python
import json, sys, os
events = json.load(sys.stdin)['events']
stages = os.environ.get('STAGES','').split()
entered, exited, failed = set(), set(), set()
for e in events:
    s = (e.get('stateEnteredEventDetails') or {}).get('name','')
    x = (e.get('stateExitedEventDetails')  or {}).get('name','')
    if s: entered.add(s)
    if x: exited.add(x)
    if e['type'] in ('TaskFailed','MapStateFailed','ExecutionFailed'):
        for n in list(entered - exited): failed.add(n)
for stage in stages:
    if stage in exited:    icon = chr(10003)
    elif stage in failed:  icon = chr(10007)
    elif stage in entered: icon = chr(9654)
    else:                  icon = chr(183)
    print(f'  {icon}  {stage}')
```

**Primary analog:** `scripts/ops/diagnose-execution.sh` lines 115-134 — identical entered/exited/failed pattern with same set arithmetic:
```python
import json, sys
events = json.load(sys.stdin)['events']
entered, exited, failed = set(), set(), set()
for e in events:
    s = (e.get('stateEnteredEventDetails') or {}).get('name','')
    x = (e.get('stateExitedEventDetails')  or {}).get('name','')
    if s: entered.add(s)
    if x: exited.add(x)
    if e['type'] in ('TaskFailed','MapStateFailed','ExecutionFailed'):
        for n in list(entered - exited): failed.add(n)
for stage in sorted(exited | entered | failed, key=lambda s: next(
        (i for i,e in enumerate(events)
         if (e.get('stateEnteredEventDetails') or {}).get('name') == s), 9999)):
    if stage in exited:    icon = chr(10003)
    elif stage in failed:  icon = chr(10007)
    elif stage in entered: icon = '▶'
    else:                  icon = chr(183)
    print(f'  {icon}  {stage}')
```

**Pattern to apply (D-05):** After the event loop (after `failed.add(n)`), before the per-stage rendering loop, insert a named `active` set and an assert:

```python
    if e['type'] in ('TaskFailed','MapStateFailed','ExecutionFailed'):
        for n in list(entered - exited): failed.add(n)
active = entered - exited - failed
assert len(active) <= 1, f"one-▶ invariant violation: {active}"
for stage in stages:
    ...
```

The `active` variable computed here is used by the rendering loop to determine the `▶` icon. The current loop uses `elif stage in entered:` — after the assert is inserted, the rendering loop may optionally be updated to use `elif stage in active:` for clarity (equivalent behavior for valid states, but more self-documenting). See CONTEXT.md D-05 for the authoritative spec.

**Pattern precedent for bare `assert` in operator scripts:** Operator scripts in this repo use direct Python expressions without try/except wrapping for invariant checks — the script is expected to fail loudly on unexpected state (consistent with `set -euo pipefail` in the outer bash). No additional error handling is needed.

---

#### Edit site 3: D-06 code comment on TaskFailed line

**Location:** `scripts/ops/status.sh`, line 126 — the `TaskFailed` type check

**Current code** (line 126):
```python
    if e['type'] in ('TaskFailed','MapStateFailed','ExecutionFailed'):
```

**Pattern to apply (D-06):** Add a one-line comment immediately above this line:
```python
    # TaskFailed is intermediate — stage may show ✗ briefly before retry completes
    if e['type'] in ('TaskFailed','MapStateFailed','ExecutionFailed'):
```

**Comment style precedent:** Inline comments in the embedded Python blocks are already present in `status.sh` (e.g., line 79: `# When there is a RUNNING execution, suppress old FAILED/ABORTED noise.`) — same style: plain `#` comment on its own line, one level of indentation matching the surrounding code.

---

## Shared Patterns

### Bash-to-Python stdin pipe pattern
**Source:** `scripts/ops/status.sh` lines 61-94, 116-134, 168-185
**Apply to:** All embedded Python blocks in this file (already established — do not change)

```bash
echo "$json_var" | python3 -c "
import json, sys
data = json.load(sys.stdin)
...
"
```

### Environment variable passthrough to embedded Python
**Source:** `scripts/ops/status.sh` line 116
**Apply to:** The stage-progress block (already established — do not change)

```bash
echo "$history" | STAGES="$stages_str" python3 -c "
import json, sys, os
stages = os.environ.get('STAGES','').split()
...
"
```

### No auth / no error handling patterns
Not applicable. This is a read-only operator diagnostic script. No auth guards, no centralized error handling, no validation schemas. Failures surface via `set -euo pipefail` and AWS CLI exit codes.

---

## No Analog Found

All three edits follow patterns already established in `scripts/ops/status.sh` itself or in the sibling `scripts/ops/diagnose-execution.sh`. There are no novel architectural patterns in this phase.

The `assert` statement (D-05) is the one construct with no existing precedent in these scripts — treat the CONTEXT.md D-05 code block as the authoritative spec for exact placement and syntax:

```python
active = entered - exited - failed
assert len(active) <= 1, f"one-▶ invariant violation: {active}"
```

---

## Metadata

**Analog search scope:** `scripts/ops/` (all 15 files)
**Files read:** `scripts/ops/status.sh` (full), `scripts/ops/diagnose-execution.sh` (full), `scripts/ops/trigger.sh` (full), `infra/scripts/deploy-aws-application.sh` (lines 1383-1403, 1510-1530, 1645-1724)
**Stage names verified against deploy script:** All 5 state machines confirmed matching
**Pattern extraction date:** 2026-05-16
