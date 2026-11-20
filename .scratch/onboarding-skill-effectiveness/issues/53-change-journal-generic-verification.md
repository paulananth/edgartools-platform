# change-journal: Specify generic verification

Type: task
Status: open
Priority: P1
Blocked by: 05, 47, 52
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [change-journal](../../../skills/change-journal/SKILL.md)
Step: 5 of 6
Skill dependencies: bookkeeping
Applicability: Every source whose processing or publication produces journal events and delivery receipts.

## Question

Which complete behavioral scenarios prove this skill's claims, using shared tooling and source-supplied fixtures rather than copied source-specific logic?

## Scope and evidence

Propose Given–When–Then scenarios before writing test code and obtain the operator's required scenario approval. Start with: the same event delivered twice, changed processing identity and a delivery failure after a durable producer commit.

Required observable proof: assert duplicate delivery is harmless, changed processing identity is handled correctly and a delivery retry does not rerun a completed source load. Reuse existing generic workers, fixtures and harnesses; configuration and invented input data supply source differences. If tooling cannot express a behavior, link a separate capability-gap ticket rather than adding source-specific runtime code here.

Start from skills/change-journal/SKILL.md: Skipping and forcing, Required independence, Validate, Recover delivery. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Specify generic verification](./05-data-platform-generic-verification.md); [bookkeeping: Specify generic verification](./47-bookkeeping-generic-verification.md); [change-journal: Make progress resumable](./52-change-journal-resume.md)

Priority rationale: Producer completion and delivery evidence must remain distinct.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Record distinct Given–When–Then scenarios and obtain the required scenario approval before test implementation.
- [ ] Use the existing generic path to assert duplicate delivery is harmless, changed processing identity is handled correctly and a delivery retry does not rerun a completed source load.
- [ ] Record stored outcomes, affected checks and limitations; no mock-call-only, static-text or tautological proof.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
