# pipeline-orchestration: Reconcile shared rules

Type: task
Status: open
Blocked by: 85, 02
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [pipeline-orchestration](../../../skills/pipeline-orchestration/SKILL.md)
Step: 2 of 6
Applicability: Conditional: onboarding includes a recurring timer, dependency sequence or start/stop deployment.

## Question

Which local instructions conflict with or duplicate the repository's authoritative rules, and what should this skill reference?

## Scope and evidence

Audit approval, activation, provider access, secrets, configuration-only work, local proof, test-scenario approval and completion wording against current CLAUDE.md and explicit operator instructions. Keep source-phase details here and shared rules at their existing authoritative home. Record genuine unresolved decisions; do not fabricate operator approval.

Apply the shared rule disposition from the data-platform ticket to this skill's inputs and outputs: reviewed orchestration configuration, verified lifecycle behavior and rollback instructions.

Start from skills/pipeline-orchestration/SKILL.md: Establish the runnable pipeline, Keep execution ownership intact, Prove and operate. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[pipeline-orchestration: Define one responsibility](./85-pipeline-orchestration-responsibility.md); [data-platform: Reconcile shared rules](./02-data-platform-consistent-rules.md)

## Acceptance checklist

- [ ] Inventory each duplicated or conflicting instruction with its authoritative source and proposed disposition.
- [ ] Align the local phase with the shared rule decision while preserving explicit operator boundaries.
- [ ] Trace a routine path and a blocked path; confirm no new approval, provider access or switch-on authority was inferred.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
