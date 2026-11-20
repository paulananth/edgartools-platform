# bookkeeping: Define one responsibility

Type: task
Status: open
Blocked by: 01
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [bookkeeping](../../../skills/bookkeeping/SKILL.md)
Step: 1 of 6
Applicability: Every source's declared execution targets; honor the target's configured grain.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Own run plans, execution state, worker verification and recovery; source interpretation belongs to configured readers.

Inventory existing instructions against the neighboring owners: data-operations operates the run; change-journal owns delivery receipts. Reconcile the current index and references before moving any text.

Start from skills/bookkeeping/SKILL.md: Required independence, Source registration, Grain, Validate, Recover. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md)

## Acceptance checklist

- [ ] List decisions, inputs and outputs owned here using current repository evidence.
- [ ] Assign each overlapping responsibility one authoritative owner and a named handoff.
- [ ] Demonstrate the boundary on a verified step, a worker failure, a restart and a target configured with run grain; link retained work rather than duplicating it.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
