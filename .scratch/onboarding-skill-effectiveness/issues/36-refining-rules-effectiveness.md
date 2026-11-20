# refining-rules: Measure effectiveness

Type: task
Status: open
Priority: P2
Blocked by: 06, 24, 30, 35
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [refining-rules](../../../skills/refining-rules/SKILL.md)
Step: 6 of 6
Skill dependencies: data-onboarding, data-quality
Applicability: Conditional: the proposed onboarding work changes an existing source or matching policy.

## Question

Does the revised skill improve observed task outcomes compared with a recorded baseline?

## Scope and evidence

Record baseline and revised behavior on comparable representative tasks: a new mapping on an existing feed, a changed identifier rule and an unchanged delivery. Measure unnecessary re-onboarding, repeated unchanged proofs, unintended identity movement and rollback readiness. Record task inputs, skill revisions, active versus waiting time, command outcomes and limitations; do not claim improvement from shorter text alone.

Carry unchanged evidence forward. Choose acceptance targets before the comparison and retain any regression or unavailable live proof explicitly.

Start from skills/refining-rules/SKILL.md: Shared with Data Onboarding, change-mapping, change-quality, change-matching, check and load. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Measure effectiveness](./06-data-platform-effectiveness.md); [data-onboarding: Measure effectiveness](./24-data-onboarding-effectiveness.md); [data-quality: Measure effectiveness](./30-data-quality-effectiveness.md); [refining-rules: Specify generic verification](./35-refining-rules-generic-verification.md)

Priority rationale: Conditional path for existing-source revisions.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Record a reproducible baseline and predeclared improvement targets for unnecessary re-onboarding, repeated unchanged proofs, unintended identity movement and rollback readiness.
- [ ] Compare the revised skill on matching scenarios; attribute waiting time and unavailable evidence explicitly.
- [ ] Report measured gains and regressions, remaining limitations and whether the targets were met.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
