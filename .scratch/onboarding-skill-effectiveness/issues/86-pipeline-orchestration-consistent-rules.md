# pipeline-orchestration: Reconcile shared rules

Type: task
Status: open
Priority: P3
Blocked by: 02, 44, 50, 56, 85
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [pipeline-orchestration](../../../skills/pipeline-orchestration/SKILL.md)
Step: 2 of 6
Skill dependencies: data-operations, bookkeeping, change-journal
Applicability: Conditional: onboarding includes a recurring timer, dependency sequence or start/stop deployment.

## Question

Which local instructions conflict with or duplicate the repository's authoritative rules, and what should this skill reference?

## Scope and evidence

Audit approval, activation, provider access, secrets, configuration-only work, local proof, test-scenario approval and completion wording against current CLAUDE.md and explicit operator instructions. Keep source-phase details here and shared rules at their existing authoritative home. Record genuine unresolved decisions; do not fabricate operator approval.

Apply the shared rule disposition from the data-platform ticket to this skill's inputs and outputs: reviewed orchestration configuration, verified lifecycle behavior and rollback instructions.

Start from skills/pipeline-orchestration/SKILL.md: Establish the runnable pipeline, Keep execution ownership intact, Prove and operate. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Reconcile shared rules](./02-data-platform-consistent-rules.md); [bookkeeping: Reconcile shared rules](./44-bookkeeping-consistent-rules.md); [change-journal: Reconcile shared rules](./50-change-journal-consistent-rules.md); [data-operations: Reconcile shared rules](./56-data-operations-consistent-rules.md); [pipeline-orchestration: Define one responsibility](./85-pipeline-orchestration-responsibility.md)

Priority rationale: Scheduling follows a verified runnable source.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Inventory each duplicated or conflicting instruction with its authoritative source and proposed disposition.
- [ ] Align the local phase with the shared rule decision while preserving explicit operator boundaries.
- [ ] Trace a routine path and a blocked path; confirm no new approval, provider access or switch-on authority was inferred.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
