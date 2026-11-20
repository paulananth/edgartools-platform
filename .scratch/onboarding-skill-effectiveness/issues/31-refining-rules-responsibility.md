# refining-rules: Define one responsibility

Type: task
Status: open
Priority: P2
Blocked by: 01, 19, 25
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [refining-rules](../../../skills/refining-rules/SKILL.md)
Step: 1 of 6
Skill dependencies: data-onboarding, data-quality
Applicability: Conditional: the proposed onboarding work changes an existing source or matching policy.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Measure and apply a revision to existing mappings, quality or matching while preserving the prior version and proof.

Inventory existing instructions against the neighboring owners: data-onboarding only for genuinely new parts; data-operations for execution. Reconcile the current index and references before moving any text.

Start from skills/refining-rules/SKILL.md: Shared with Data Onboarding, change-mapping, change-quality, change-matching, check and load. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md); [data-onboarding: Define one responsibility](./19-data-onboarding-responsibility.md); [data-quality: Define one responsibility](./25-data-quality-responsibility.md)

Priority rationale: Conditional path for existing-source revisions.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] List decisions, inputs and outputs owned here using current repository evidence.
- [ ] Assign each overlapping responsibility one authoritative owner and a named handoff.
- [ ] Demonstrate the boundary on a new mapping on an existing feed, a changed identifier rule and an unchanged delivery; link retained work rather than duplicating it.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
