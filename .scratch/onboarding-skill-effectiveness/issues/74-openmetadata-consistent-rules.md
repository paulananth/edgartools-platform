# openmetadata: Reconcile shared rules

Type: task
Status: open
Priority: P2
Blocked by: 02, 68, 73
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [openmetadata](../../../skills/openmetadata/SKILL.md)
Step: 2 of 6
Skill dependencies: data-catalog
Applicability: Conditional: OpenMetadata is the configured catalog destination.

## Question

Which local instructions conflict with or duplicate the repository's authoritative rules, and what should this skill reference?

## Scope and evidence

Audit approval, activation, provider access, secrets, configuration-only work, local proof, test-scenario approval and completion wording against current CLAUDE.md and explicit operator instructions. Keep source-phase details here and shared rules at their existing authoritative home. Record genuine unresolved decisions; do not fabricate operator approval.

Apply the shared rule disposition from the data-platform ticket to this skill's inputs and outputs: published native objects, readback reconciliation and separate status for each publication family.

Start from skills/openmetadata/SKILL.md: Readback and reconciliation traps, Operator outcome report, Pipeline execution boundary. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

Coordinate with [Move the business-meaning passages out of the openmetadata skill](../../catalog-skill-routing/issues/02-move-business-meaning-out-of-the-openmetadata-skill.md). That ticket remains the owner of its exact text moves; this ticket consumes its result or links any overlap rather than creating a competing implementation.

## Prerequisites

[data-platform: Reconcile shared rules](./02-data-platform-consistent-rules.md); [data-catalog: Reconcile shared rules](./68-data-catalog-consistent-rules.md); [openmetadata: Define one responsibility](./73-openmetadata-responsibility.md)

Priority rationale: Conditional destination adapter consumes catalog expectations.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Inventory each duplicated or conflicting instruction with its authoritative source and proposed disposition.
- [ ] Align the local phase with the shared rule decision while preserving explicit operator boundaries.
- [ ] Trace a routine path and a blocked path; confirm no new approval, provider access or switch-on authority was inferred.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
