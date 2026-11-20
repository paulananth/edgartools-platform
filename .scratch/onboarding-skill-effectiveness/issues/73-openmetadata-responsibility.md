# openmetadata: Define one responsibility

Type: task
Status: open
Priority: P2
Blocked by: 01, 67
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [openmetadata](../../../skills/openmetadata/SKILL.md)
Step: 1 of 6
Skill dependencies: data-catalog
Applicability: Conditional: OpenMetadata is the configured catalog destination.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Own OpenMetadata object mapping, supported publication commands and API readback; business meaning remains in data-catalog.

Inventory existing instructions against the neighboring owners: data-catalog judges semantic completeness; data-operations owns source execution. Reconcile the current index and references before moving any text.

Start from skills/openmetadata/SKILL.md: Readback and reconciliation traps, Operator outcome report, Pipeline execution boundary. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

Coordinate with [Move the business-meaning passages out of the openmetadata skill](../../catalog-skill-routing/issues/02-move-business-meaning-out-of-the-openmetadata-skill.md). That ticket remains the owner of its exact text moves; this ticket consumes its result or links any overlap rather than creating a competing implementation.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md); [data-catalog: Define one responsibility](./67-data-catalog-responsibility.md)

Priority rationale: Conditional destination adapter consumes catalog expectations.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] List decisions, inputs and outputs owned here using current repository evidence.
- [ ] Assign each overlapping responsibility one authoritative owner and a named handoff.
- [ ] Demonstrate the boundary on successful publication, a partial API failure, stale objects and an unchanged second publication; link retained work rather than duplicating it.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
