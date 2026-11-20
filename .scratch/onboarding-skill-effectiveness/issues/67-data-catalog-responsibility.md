# data-catalog: Define one responsibility

Type: task
Status: open
Priority: P1
Blocked by: 01, 19, 25, 61
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-catalog](../../../skills/data-catalog/SKILL.md)
Step: 1 of 6
Skill dependencies: data-governance, data-onboarding, data-quality
Applicability: Every source's business metadata and steward-facing publication.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Own domains, glossaries, asset meaning and destination-independent publication expectations.

Inventory existing instructions against the neighboring owners: openmetadata or another destination skill owns API mechanics and readback. Reconcile the current index and references before moving any text.

Start from skills/data-catalog/SKILL.md: Use the skill that owns the decision, Choose the catalog's own skill, Report publication as separate outcomes. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

Coordinate with [Move the business-meaning passages out of the openmetadata skill](../../catalog-skill-routing/issues/02-move-business-meaning-out-of-the-openmetadata-skill.md). That ticket remains the owner of its exact text moves; this ticket consumes its result or links any overlap rather than creating a competing implementation.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md); [data-onboarding: Define one responsibility](./19-data-onboarding-responsibility.md); [data-quality: Define one responsibility](./25-data-quality-responsibility.md); [data-governance: Define one responsibility](./61-data-governance-responsibility.md)

Priority rationale: Business metadata consumes the model, targets and checks.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] List decisions, inputs and outputs owned here using current repository evidence.
- [ ] Assign each overlapping responsibility one authoritative owner and a named handoff.
- [ ] Demonstrate the boundary on a source spanning multiple domains, a relationship asset and a quality definition published to one catalog; link retained work rather than duplicating it.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
