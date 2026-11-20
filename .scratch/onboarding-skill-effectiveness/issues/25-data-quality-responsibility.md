# data-quality: Define one responsibility

Type: task
Status: open
Priority: P0
Blocked by: 01, 07, 13
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-quality](../../../skills/data-quality/SKILL.md)
Step: 1 of 6
Skill dependencies: data-profiling, data-modeling
Applicability: Every source with field constraints, defects or downstream quality obligations.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Translate measured defects and governed requirements into checks, dispositions and quality evidence.

Inventory existing instructions against the neighboring owners: data-onboarding or refining-rules; data-catalog owns the checks' business meaning. Reconcile the current index and references before moving any text.

Start from skills/data-quality/SKILL.md: plan, measure, decide, write, Publish quality meaning to the business catalog. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md); [data-profiling: Define one responsibility](./07-data-profiling-responsibility.md); [data-modeling: Define one responsibility](./13-data-modeling-responsibility.md)

Priority rationale: Measured checks and dispositions prevent unsafe mappings.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] List decisions, inputs and outputs owned here using current repository evidence.
- [ ] Assign each overlapping responsibility one authoritative owner and a named handoff.
- [ ] Demonstrate the boundary on valid and invalid rows, a deferred identity and a failing check that must survive into stored quality evidence; link retained work rather than duplicating it.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
