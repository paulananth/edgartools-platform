# data-modeling: Measure effectiveness

Type: task
Status: open
Priority: P0
Blocked by: 06, 12, 17
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-modeling](../../../skills/data-modeling/SKILL.md)
Step: 6 of 6
Skill dependencies: data-profiling
Applicability: Every new part whose class, identity, relationship or destination needs mapping.

## Question

Does the revised skill improve observed task outcomes compared with a recorded baseline?

## Scope and evidence

Record baseline and revised behavior on comparable representative tasks: a shared issued identifier, an ambiguous name, a cross-reference-only identifier and an effective-dated relationship. Measure unsupported modeling assumptions, reopened decisions, downstream remapping and time to an evidence-backed model. Record task inputs, skill revisions, active versus waiting time, command outcomes and limitations; do not claim improvement from shorter text alone.

Carry unchanged evidence forward. Choose acceptance targets before the comparison and retain any regression or unavailable live proof explicitly.

Start from skills/data-modeling/SKILL.md: Decision rules, Workflow, Prove the model on the data before building. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Measure effectiveness](./06-data-platform-effectiveness.md); [data-profiling: Measure effectiveness](./12-data-profiling-effectiveness.md); [data-modeling: Specify generic verification](./17-data-modeling-generic-verification.md)

Priority rationale: Identity and destination decisions precede configuration.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Record a reproducible baseline and predeclared improvement targets for unsupported modeling assumptions, reopened decisions, downstream remapping and time to an evidence-backed model.
- [ ] Compare the revised skill on matching scenarios; attribute waiting time and unavailable evidence explicitly.
- [ ] Report measured gains and regressions, remaining limitations and whether the targets were met.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
