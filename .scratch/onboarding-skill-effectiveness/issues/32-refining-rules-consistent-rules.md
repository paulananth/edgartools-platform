# refining-rules: Reconcile shared rules

Type: task
Status: open
Priority: P2
Blocked by: 02, 20, 26, 31
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [refining-rules](../../../skills/refining-rules/SKILL.md)
Step: 2 of 6
Skill dependencies: data-onboarding, data-quality
Applicability: Conditional: the proposed onboarding work changes an existing source or matching policy.

## Question

Which local instructions conflict with or duplicate the repository's authoritative rules, and what should this skill reference?

## Scope and evidence

Audit approval, activation, provider access, secrets, configuration-only work, local proof, test-scenario approval and completion wording against current CLAUDE.md and explicit operator instructions. Keep source-phase details here and shared rules at their existing authoritative home. Record genuine unresolved decisions; do not fabricate operator approval.

Apply the shared rule disposition from the data-platform ticket to this skill's inputs and outputs: a measured rules delta, regenerated Mapping Documents and the exact revised version's proof.

Start from skills/refining-rules/SKILL.md: Shared with Data Onboarding, change-mapping, change-quality, change-matching, check and load. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Reconcile shared rules](./02-data-platform-consistent-rules.md); [data-onboarding: Reconcile shared rules](./20-data-onboarding-consistent-rules.md); [data-quality: Reconcile shared rules](./26-data-quality-consistent-rules.md); [refining-rules: Define one responsibility](./31-refining-rules-responsibility.md)

Priority rationale: Conditional path for existing-source revisions.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Inventory each duplicated or conflicting instruction with its authoritative source and proposed disposition.
- [ ] Align the local phase with the shared rule decision while preserving explicit operator boundaries.
- [ ] Trace a routine path and a blocked path; confirm no new approval, provider access or switch-on authority was inferred.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
