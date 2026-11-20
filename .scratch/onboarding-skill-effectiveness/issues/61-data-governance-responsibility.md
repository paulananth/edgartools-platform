# data-governance: Define one responsibility

Type: task
Status: open
Priority: P1
Blocked by: 01, 13
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-governance](../../../skills/data-governance/SKILL.md)
Step: 1 of 6
Skill dependencies: data-modeling
Applicability: Every source's governed outputs and lineage claims.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Define which source-to-output evidence and lineage a steward may trust, independently of catalog-specific mechanics.

Inventory existing instructions against the neighboring owners: data-catalog for business presentation and a destination-specific skill for publication. Reconcile the current index and references before moving any text.

Start from skills/data-governance/SKILL.md: What is governed, Completion; LINEAGE.md. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md); [data-modeling: Define one responsibility](./13-data-modeling-responsibility.md)

Priority rationale: Governed output and lineage meaning precede catalog presentation.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] List decisions, inputs and outputs owned here using current repository evidence.
- [ ] Assign each overlapping responsibility one authoritative owner and a named handoff.
- [ ] Demonstrate the boundary on a governed input, a transient intermediate, a failed processing step and a trusted output; link retained work rather than duplicating it.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
