# pipeline-orchestration: Define one responsibility

Type: task
Status: open
Priority: P3
Blocked by: 01, 43, 49, 55
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [pipeline-orchestration](../../../skills/pipeline-orchestration/SKILL.md)
Step: 1 of 6
Skill dependencies: data-operations, bookkeeping, change-journal
Applicability: Conditional: onboarding includes a recurring timer, dependency sequence or start/stop deployment.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Own schedule and lifecycle configuration after the source is runnable, preserving execution and delivery ownership.

Inventory existing instructions against the neighboring owners: data-operations runs source work; bookkeeping owns execution state and change-journal owns delivery. Reconcile the current index and references before moving any text.

Start from skills/pipeline-orchestration/SKILL.md: Establish the runnable pipeline, Keep execution ownership intact, Prove and operate. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md); [bookkeeping: Define one responsibility](./43-bookkeeping-responsibility.md); [change-journal: Define one responsibility](./49-change-journal-responsibility.md); [data-operations: Define one responsibility](./55-data-operations-responsibility.md)

Priority rationale: Scheduling follows a verified runnable source.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] List decisions, inputs and outputs owned here using current repository evidence.
- [ ] Assign each overlapping responsibility one authoritative owner and a named handoff.
- [ ] Demonstrate the boundary on a disabled schedule, a failed dependency, a restart and an explicit switch-on boundary; link retained work rather than duplicating it.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
