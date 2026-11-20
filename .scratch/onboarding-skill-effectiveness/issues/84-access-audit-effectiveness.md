# access-audit: Measure effectiveness

Type: task
Status: open
Priority: P1
Blocked by: 06, 83
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [access-audit](../../../skills/access-audit/SKILL.md)
Step: 6 of 6
Skill dependencies: data-platform
Applicability: Review the skill or access changes being finalized; run only applicable read-only platform checks.

## Question

Does the revised skill improve observed task outcomes compared with a recorded baseline?

## Scope and evidence

Record baseline and revised behavior on comparable representative tasks: a restricted runtime role, a denied audit view and an overprivileged role detected without mutation. Measure unsupported PASS claims, missing control coverage, unnecessary privileged access and audit duration. Record task inputs, skill revisions, active versus waiting time, command outcomes and limitations; do not claim improvement from shorter text alone.

Carry unchanged evidence forward. Choose acceptance targets before the comparison and retain any regression or unavailable live proof explicitly.

Start from skills/access-audit/SKILL.md: Hard stops, Objectives, The gate before finalising a skill role or login. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Measure effectiveness](./06-data-platform-effectiveness.md); [access-audit: Specify generic verification](./83-access-audit-generic-verification.md)

Priority rationale: Independent access evidence is cross-cutting; remediation is separate.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Record a reproducible baseline and predeclared improvement targets for unsupported PASS claims, missing control coverage, unnecessary privileged access and audit duration.
- [ ] Compare the revised skill on matching scenarios; attribute waiting time and unavailable evidence explicitly.
- [ ] Report measured gains and regressions, remaining limitations and whether the targets were met.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
