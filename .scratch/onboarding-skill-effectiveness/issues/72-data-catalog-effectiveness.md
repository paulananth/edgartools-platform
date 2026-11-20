# data-catalog: Measure effectiveness

Type: task
Status: open
Priority: P1
Blocked by: 06, 24, 30, 66, 71
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-catalog](../../../skills/data-catalog/SKILL.md)
Step: 6 of 6
Skill dependencies: data-governance, data-onboarding, data-quality
Applicability: Every source's business metadata and steward-facing publication.

## Question

Does the revised skill improve observed task outcomes compared with a recorded baseline?

## Scope and evidence

Record baseline and revised behavior on comparable representative tasks: a source spanning multiple domains, a relationship asset and a quality definition published to one catalog. Measure missing business meaning, destination-specific leakage, duplicate publication and reconciliation failures. Record task inputs, skill revisions, active versus waiting time, command outcomes and limitations; do not claim improvement from shorter text alone.

Carry unchanged evidence forward. Choose acceptance targets before the comparison and retain any regression or unavailable live proof explicitly.

Start from skills/data-catalog/SKILL.md: Use the skill that owns the decision, Choose the catalog's own skill, Report publication as separate outcomes. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

Coordinate with [Move the business-meaning passages out of the openmetadata skill](../../catalog-skill-routing/issues/02-move-business-meaning-out-of-the-openmetadata-skill.md). That ticket remains the owner of its exact text moves; this ticket consumes its result or links any overlap rather than creating a competing implementation.

## Prerequisites

[data-platform: Measure effectiveness](./06-data-platform-effectiveness.md); [data-onboarding: Measure effectiveness](./24-data-onboarding-effectiveness.md); [data-quality: Measure effectiveness](./30-data-quality-effectiveness.md); [data-governance: Measure effectiveness](./66-data-governance-effectiveness.md); [data-catalog: Specify generic verification](./71-data-catalog-generic-verification.md)

Priority rationale: Business metadata consumes the model, targets and checks.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Record a reproducible baseline and predeclared improvement targets for missing business meaning, destination-specific leakage, duplicate publication and reconciliation failures.
- [ ] Compare the revised skill on matching scenarios; attribute waiting time and unavailable evidence explicitly.
- [ ] Report measured gains and regressions, remaining limitations and whether the targets were met.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
