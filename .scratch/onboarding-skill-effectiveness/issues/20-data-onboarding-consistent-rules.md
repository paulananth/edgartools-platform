# data-onboarding: Reconcile shared rules

Type: task
Status: open
Blocked by: 19, 02
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-onboarding](../../../skills/data-onboarding/SKILL.md)
Step: 2 of 6
Applicability: Every new source or new kind; live-source revisions route to refining-rules.

## Question

Which local instructions conflict with or duplicate the repository's authoritative rules, and what should this skill reference?

## Scope and evidence

Audit approval, activation, provider access, secrets, configuration-only work, local proof, test-scenario approval and completion wording against current CLAUDE.md and explicit operator instructions. Keep source-phase details here and shared rules at their existing authoritative home. Record genuine unresolved decisions; do not fabricate operator approval.

Apply the shared rule disposition from the data-platform ticket to this skill's inputs and outputs: checked source configuration, target registration, quality configuration, Mapping Documents and a handoff record.

Start from skills/data-onboarding/SKILL.md: Modes in order, The files are the rules, metadata, check and load; MAP.md and TARGETS.md. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

The prior split is recorded in [The data-onboarding skill is split behind pointers](../../rebuild-priorities/issues/215-split-the-data-onboarding-skill.md); inspect current references before repeating it.

## Prerequisites

[data-onboarding: Define one responsibility](./19-data-onboarding-responsibility.md); [data-platform: Reconcile shared rules](./02-data-platform-consistent-rules.md)

## Acceptance checklist

- [ ] Inventory each duplicated or conflicting instruction with its authoritative source and proposed disposition.
- [ ] Align the local phase with the shared rule decision while preserving explicit operator boundaries.
- [ ] Trace a routine path and a blocked path; confirm no new approval, provider access or switch-on authority was inferred.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
