# mdm-engineering: Define one responsibility

Type: task
Status: open
Priority: P2
Blocked by: 01, 13
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [mdm-engineering](../../../skills/mdm-engineering/SKILL.md)
Step: 1 of 6
Skill dependencies: data-modeling
Applicability: Conditional: choose mastering proof or investigate a demonstrated engine or storage gap; configuration remains the default.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Own merge and storage behavior and proof selection; do not turn a source mapping task into an engine refactor.

Inventory existing instructions against the neighboring owners: data-onboarding or refining-rules when configuration suffices; separate implementation work for a real gap. Reconcile the current index and references before moving any text.

Start from skills/mdm-engineering/SKILL.md: Hard stops, Choose the cheapest proof, Independent installed qualification. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md); [data-modeling: Define one responsibility](./13-data-modeling-responsibility.md)

Priority rationale: Conditional mastering proof or demonstrated engine gap.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] List decisions, inputs and outputs owned here using current repository evidence.
- [ ] Assign each overlapping responsibility one authoritative owner and a named handoff.
- [ ] Demonstrate the boundary on a conflicting identifier, a relationship with a missing endpoint and a merge retry after interruption; link retained work rather than duplicating it.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
