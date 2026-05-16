# Phase 2: Status Completeness - Context

**Gathered:** 2026-05-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Verify and fix `scripts/ops/status.sh` so it shows a complete, accurate stage-level
breakdown for all 5 registered state machines, with a correct active-stage marker (▶)
during any running pipeline. The stage lists are already hardcoded and match the actual
state machine definitions today — the primary work is: (1) adding a maintenance comment
to the MACHINES array, (2) adding a Python assert for the one-▶ invariant in the
stage-progress block, and (3) fixing any edge cases discovered during code inspection.

What this phase does NOT do: add retry-state visualization (known limitation — see D-07),
change the output format beyond what's needed to satisfy OBS-03/OBS-04, touch any state
machine definitions, or add live end-to-end tests of all 5 machines.

</domain>

<decisions>
## Implementation Decisions

### Stage list maintenance
- **D-01:** [informational] Keep the stage lists hardcoded in the `MACHINES` array in `status.sh`. Do NOT
  generate them dynamically at runtime (no extra API call on every status.sh invocation).
- **D-02:** Add a comment directly above the `MACHINES` array pointing reviewers to the
  source of truth:
  `# Stage order must match write_bootstrap_phased_definition(), write_silver_mdm_gold_definition(), etc. in infra/scripts/deploy-aws-application.sh`
- **D-03:** [informational] No live verification pass is needed — code inspection confirms the lists match
  the state machine definitions. Running actual pipelines to spot-check is out of scope.

### Active-stage display
- **D-04:** [informational] The two-section layout is correct and sufficient: `▶ BatchBootstrap` in
  STAGE PROGRESS + the separate BATCH MAP RUN section below. Do NOT merge the batch item
  count into the stage line.
- **D-05:** Exactly one `▶` marker is the invariant for OBS-04. The plan resolves the
  D-03/D-05 tension as follows: add a Python `assert` in the stage-progress block,
  immediately after computing the active set and before the per-stage rendering loop:
  ```python
  active = entered - exited - failed
  assert len(active) <= 1, f"one-▶ invariant violation: {active}"
  for stage in stages:
      ...
  ```
  This is a code-level verification that requires no live run (satisfies D-03) and
  enforces the invariant structurally (satisfies D-05). The Step Functions sequential
  execution model guarantees `len(active) <= 1` in practice — the assert documents and
  enforces this guarantee. Place it after the event-loop that builds `entered`,
  `exited`, and `failed`, before the stage-icon rendering loop.

### Retry-state behavior (known limitation)
- **D-06:** `✗` during a Step Functions retry is expected behavior and is NOT a bug to fix
  in Phase 2. Sequence: ECS task fails → `TaskFailed` fires → stage enters `failed` set →
  shows `✗`. If Step Functions retries and succeeds, the stage will transition to `✓` when
  it exits. This transient `✗` is a known limitation for v1. Future phases MAY address it
  by distinguishing `TaskFailed` (intermediate) from `ExecutionFailed`/`MapStateFailed`
  (terminal), but that work is explicitly deferred. Do not "fix" this behavior in Phase 2.

### Claude's Discretion
- **Retry-state visualization:** Addressed by D-06 — keep current `✗` behavior. No new
  icon or logic change for retry states.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The file being modified
- `scripts/ops/status.sh` — the entire file; the `MACHINES` array (lines ~35–41), the
  `show_machine()` function's stage-progress Python block (lines ~116–133), and the
  active-stage logic (entered/exited/failed sets) are the primary edit targets

### Source of truth for stage names
- `infra/scripts/deploy-aws-application.sh` — specifically:
  - `write_bootstrap_phased_definition()` (~line 1385–1403): States dict keys are
    `SeedUniverse`, `BatchBootstrap`, `MdmRun`, `MdmBackfill`, `MdmSync`, `MdmVerify`, `GoldRefresh`
  - `write_silver_mdm_gold_definition()` (~line 1517–1527): States dict keys are
    `SeedSilverBatches`, `BatchSilver`, `MdmRun`, `MdmBackfill`, `MdmSync`, `MdmVerify`, `GoldRefresh`
  - `write_mdm_gold_definition()` (~line 1651–1656): `MdmRun`, `MdmBackfill`, `MdmSync`, `MdmVerify`, `GoldRefresh`
  - `write_ownership_mdm_gold_definition()` (~line 1714–1722): `ParseOwnershipBronze`, `MdmRun`, `MdmBackfill`, `MdmSync`, `MdmVerify`, `GoldRefresh`
  - `gold-refresh` state machine: single state `GoldRefresh`

### Phase requirements
- `.planning/workstreams/fix-pipelines/REQUIREMENTS.md` — OBS-03 (complete stage breakdown),
  OBS-04 (active stage marker)
- `.planning/workstreams/fix-pipelines/ROADMAP.md` Phase 2 — success criteria

### Prior phase context (active-stage logic pattern)
- `.planning/workstreams/fix-pipelines/phases/01-failure-surfacing/01-CONTEXT.md` —
  D-05 describes existing `status.sh` polling patterns used as reference

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `MACHINES` array in `status.sh` (~line 35): `"short|LABEL|sm-suffix|Stage1 Stage2 ..."` —
  the edit target for the maintenance comment. Five entries, one per state machine.
- Stage-progress Python block inside `show_machine()` (lines ~116–133): reads
  `get-execution-history` events, builds `entered`/`exited`/`failed` sets, maps each stage
  to an icon. Edit target for the one-▶ assert (D-05).

### Established Patterns
- Active-stage detection uses set arithmetic: `entered - exited` → stages currently running.
  Already working correctly for the non-retry happy path.
- `aws_ stepfunctions get-execution-history` is already called in `show_machine()`; no new
  AWS API calls are needed for OBS-04.

### Integration Points
- Only `scripts/ops/status.sh` is modified in this phase. No state machine definitions,
  no deploy scripts, no Terraform.

</code_context>

<specifics>
## Specific Ideas

- The comment for D-02 should be placed immediately above the `declare -a MACHINES=(` line
  so it's unmissable when editing the array.
- The one-▶ assert (D-05): compute `active = entered - exited - failed` as a named variable,
  assert `len(active) <= 1`, then use `active` inside the per-stage rendering loop to
  determine the ▶ icon. This makes the code self-documenting.
- D-06 known limitation: add a one-line code comment near the `TaskFailed` detection:
  `# TaskFailed is intermediate — stage may show ✗ briefly before retry completes`

</specifics>

<deferred>
## Deferred Ideas

- Retry-state icon upgrade (▶ or ↻ during retry window) — would require distinguishing
  `TaskFailed` (intermediate) from `MapStateFailed`/`ExecutionFailed` (terminal). Deferred
  to a future phase; D-06 explicitly calls this out as a known limitation.

</deferred>

---

*Phase: 02-status-completeness*
*Context gathered: 2026-05-16*
