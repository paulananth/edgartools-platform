# bookkeeping: Measure effectiveness

Type: task
Status: open
Priority: P1
Blocked by: 06, 24, 47
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [bookkeeping](../../../skills/bookkeeping/SKILL.md)
Step: 6 of 6
Skill dependencies: data-onboarding
Applicability: Every source's declared execution targets; honor the target's configured grain.

## Question

Does the revised skill improve observed task outcomes compared with a recorded baseline?

## Scope and evidence

Record baseline and revised behavior on comparable representative tasks: a verified step, a worker failure, a restart and a target configured with run grain. Measure duplicate work after restart, unverified successes, wrong-grain overhead and recovery duration. Record task inputs, skill revisions, active versus waiting time, command outcomes and limitations; do not claim improvement from shorter text alone.

Carry unchanged evidence forward. Choose acceptance targets before the comparison and retain any regression or unavailable live proof explicitly.

Start from skills/bookkeeping/SKILL.md: Required independence, Source registration, Grain, Validate, Recover. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Measure effectiveness](./06-data-platform-effectiveness.md); [data-onboarding: Measure effectiveness](./24-data-onboarding-effectiveness.md); [bookkeeping: Specify generic verification](./47-bookkeeping-generic-verification.md)

Priority rationale: Configured targets must execute with verified recovery.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Record a reproducible baseline and predeclared improvement targets for duplicate work after restart, unverified successes, wrong-grain overhead and recovery duration.
- [ ] Compare the revised skill on matching scenarios; attribute waiting time and unavailable evidence explicitly.
- [ ] Report measured gains and regressions, remaining limitations and whether the targets were met.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
