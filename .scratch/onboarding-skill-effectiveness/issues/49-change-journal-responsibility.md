# change-journal: Define one responsibility

Type: task
Status: open
Blocked by: 01
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [change-journal](../../../skills/change-journal/SKILL.md)
Step: 1 of 6
Applicability: Every source whose processing or publication produces journal events and delivery receipts.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Own durable change events, receipts, skip identity and delivery recovery without taking ownership of source execution.

Inventory existing instructions against the neighboring owners: data-operations reports completion; producer and bookkeeping owners recover their own execution. Reconcile the current index and references before moving any text.

Start from skills/change-journal/SKILL.md: Skipping and forcing, Required independence, Validate, Recover delivery. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md)

## Acceptance checklist

- [ ] List decisions, inputs and outputs owned here using current repository evidence.
- [ ] Assign each overlapping responsibility one authoritative owner and a named handoff.
- [ ] Demonstrate the boundary on the same event delivered twice, changed processing identity and a delivery failure after a durable producer commit; link retained work rather than duplicating it.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

