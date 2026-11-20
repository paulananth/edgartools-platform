# data-platform: Measure effectiveness

Type: task
Status: open
Priority: P0
Blocked by: 05
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-platform](../../../skills/data-platform/SKILL.md)
Step: 6 of 6
Skill dependencies: none
Applicability: Every source: route the work and discover configured connections.

## Question

Does the revised skill improve observed task outcomes compared with a recorded baseline?

## Scope and evidence

Record baseline and revised behavior on comparable representative tasks: a new captured source, an already configured source and a restart after a completed phase. Measure time to the first correct next action, wrong routes, repeated setup and unnecessary questions. Record task inputs, skill revisions, active versus waiting time, command outcomes and limitations; do not claim improvement from shorter text alone.

Carry unchanged evidence forward. Choose acceptance targets before the comparison and retain any regression or unavailable live proof explicitly.

Start from skills/data-platform/SKILL.md: Source readiness, The flow, Connection URLs and environment. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Specify generic verification](./05-data-platform-generic-verification.md)

Priority rationale: Shared routing and rule conventions unblock every track.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Record a reproducible baseline and predeclared improvement targets for time to the first correct next action, wrong routes, repeated setup and unnecessary questions.
- [ ] Compare the revised skill on matching scenarios; attribute waiting time and unavailable evidence explicitly.
- [ ] Report measured gains and regressions, remaining limitations and whether the targets were met.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
