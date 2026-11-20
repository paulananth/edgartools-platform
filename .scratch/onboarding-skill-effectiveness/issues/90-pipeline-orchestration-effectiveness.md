# pipeline-orchestration: Measure effectiveness

Type: task
Status: open
Priority: P3
Blocked by: 06, 48, 54, 60, 89
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [pipeline-orchestration](../../../skills/pipeline-orchestration/SKILL.md)
Step: 6 of 6
Skill dependencies: data-operations, bookkeeping, change-journal
Applicability: Conditional: onboarding includes a recurring timer, dependency sequence or start/stop deployment.

## Question

Does the revised skill improve observed task outcomes compared with a recorded baseline?

## Scope and evidence

Record baseline and revised behavior on comparable representative tasks: a disabled schedule, a failed dependency, a restart and an explicit switch-on boundary. Measure premature starts, duplicate runs, manual orchestration steps and recovery duration. Record task inputs, skill revisions, active versus waiting time, command outcomes and limitations; do not claim improvement from shorter text alone.

Carry unchanged evidence forward. Choose acceptance targets before the comparison and retain any regression or unavailable live proof explicitly.

Start from skills/pipeline-orchestration/SKILL.md: Establish the runnable pipeline, Keep execution ownership intact, Prove and operate. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Measure effectiveness](./06-data-platform-effectiveness.md); [bookkeeping: Measure effectiveness](./48-bookkeeping-effectiveness.md); [change-journal: Measure effectiveness](./54-change-journal-effectiveness.md); [data-operations: Measure effectiveness](./60-data-operations-effectiveness.md); [pipeline-orchestration: Specify generic verification](./89-pipeline-orchestration-generic-verification.md)

Priority rationale: Scheduling follows a verified runnable source.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Record a reproducible baseline and predeclared improvement targets for premature starts, duplicate runs, manual orchestration steps and recovery duration.
- [ ] Compare the revised skill on matching scenarios; attribute waiting time and unavailable evidence explicitly.
- [ ] Report measured gains and regressions, remaining limitations and whether the targets were met.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
