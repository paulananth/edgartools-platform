# openmetadata: Measure effectiveness

Type: task
Status: open
Priority: P2
Blocked by: 06, 72, 77
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [openmetadata](../../../skills/openmetadata/SKILL.md)
Step: 6 of 6
Skill dependencies: data-catalog
Applicability: Conditional: OpenMetadata is the configured catalog destination.

## Question

Does the revised skill improve observed task outcomes compared with a recorded baseline?

## Scope and evidence

Record baseline and revised behavior on comparable representative tasks: successful publication, a partial API failure, stale objects and an unchanged second publication. Measure HTTP successes with missing objects, duplicate objects, stale metadata and time to a reconciled publication. Record task inputs, skill revisions, active versus waiting time, command outcomes and limitations; do not claim improvement from shorter text alone.

Carry unchanged evidence forward. Choose acceptance targets before the comparison and retain any regression or unavailable live proof explicitly.

Start from skills/openmetadata/SKILL.md: Readback and reconciliation traps, Operator outcome report, Pipeline execution boundary. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

Coordinate with [Move the business-meaning passages out of the openmetadata skill](../../catalog-skill-routing/issues/02-move-business-meaning-out-of-the-openmetadata-skill.md). That ticket remains the owner of its exact text moves; this ticket consumes its result or links any overlap rather than creating a competing implementation.

## Prerequisites

[data-platform: Measure effectiveness](./06-data-platform-effectiveness.md); [data-catalog: Measure effectiveness](./72-data-catalog-effectiveness.md); [openmetadata: Specify generic verification](./77-openmetadata-generic-verification.md)

Priority rationale: Conditional destination adapter consumes catalog expectations.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Record a reproducible baseline and predeclared improvement targets for HTTP successes with missing objects, duplicate objects, stale metadata and time to a reconciled publication.
- [ ] Compare the revised skill on matching scenarios; attribute waiting time and unavailable evidence explicitly.
- [ ] Report measured gains and regressions, remaining limitations and whether the targets were met.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
