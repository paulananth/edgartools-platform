# data-operations: Measure effectiveness

Type: task
Status: open
Priority: P1
Blocked by: 06, 24, 48, 54, 59
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-operations](../../../skills/data-operations/SKILL.md)
Step: 6 of 6
Skill dependencies: data-onboarding, bookkeeping, change-journal
Applicability: Every local source qualification and operational load; hosted actions require applicable authorization.

## Question

Does the revised skill improve observed task outcomes compared with a recorded baseline?

## Scope and evidence

Record baseline and revised behavior on comparable representative tasks: a first local load, unchanged replay, a missing capture receipt and a recoverable failed step. Measure time to verified results, repeated full loads, unexplained count differences and recovery success. Record task inputs, skill revisions, active versus waiting time, command outcomes and limitations; do not claim improvement from shorter text alone.

Carry unchanged evidence forward. Choose acceptance targets before the comparison and retain any regression or unavailable live proof explicitly.

Start from skills/data-operations/SKILL.md: Start with live state, Install and enable one source, Load a capture, Operate the recurring loop. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Measure effectiveness](./06-data-platform-effectiveness.md); [data-onboarding: Measure effectiveness](./24-data-onboarding-effectiveness.md); [bookkeeping: Measure effectiveness](./48-bookkeeping-effectiveness.md); [change-journal: Measure effectiveness](./54-change-journal-effectiveness.md); [data-operations: Specify generic verification](./59-data-operations-generic-verification.md)

Priority rationale: Local load reconciliation completes operational qualification.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Record a reproducible baseline and predeclared improvement targets for time to verified results, repeated full loads, unexplained count differences and recovery success.
- [ ] Compare the revised skill on matching scenarios; attribute waiting time and unavailable evidence explicitly.
- [ ] Report measured gains and regressions, remaining limitations and whether the targets were met.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
