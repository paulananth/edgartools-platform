# access-audit: Reconcile shared rules

Type: task
Status: open
Priority: P1
Blocked by: 02, 79
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [access-audit](../../../skills/access-audit/SKILL.md)
Step: 2 of 6
Skill dependencies: data-platform
Applicability: Review the skill or access changes being finalized; run only applicable read-only platform checks.

## Question

Which local instructions conflict with or duplicate the repository's authoritative rules, and what should this skill reference?

## Scope and evidence

Audit approval, activation, provider access, secrets, configuration-only work, local proof, test-scenario approval and completion wording against current CLAUDE.md and explicit operator instructions. Keep source-phase details here and shared rules at their existing authoritative home. Record genuine unresolved decisions; do not fabricate operator approval.

Apply the shared rule disposition from the data-platform ticket to this skill's inputs and outputs: PASS, FAIL and NOT_TESTED evidence with a coverage matrix and separate remediation references.

Start from skills/access-audit/SKILL.md: Hard stops, Objectives, The gate before finalising a skill role or login. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Reconcile shared rules](./02-data-platform-consistent-rules.md); [access-audit: Define one responsibility](./79-access-audit-responsibility.md)

Priority rationale: Independent access evidence is cross-cutting; remediation is separate.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Inventory each duplicated or conflicting instruction with its authoritative source and proposed disposition.
- [ ] Align the local phase with the shared rule decision while preserving explicit operator boundaries.
- [ ] Trace a routine path and a blocked path; confirm no new approval, provider access or switch-on authority was inferred.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
