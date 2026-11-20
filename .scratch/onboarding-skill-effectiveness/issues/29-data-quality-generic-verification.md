# data-quality: Specify generic verification

Type: task
Status: open
Priority: P0
Blocked by: 05, 11, 17, 28
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-quality](../../../skills/data-quality/SKILL.md)
Step: 5 of 6
Skill dependencies: data-profiling, data-modeling
Applicability: Every source with field constraints, defects or downstream quality obligations.

## Question

Which complete behavioral scenarios prove this skill's claims, using shared tooling and source-supplied fixtures rather than copied source-specific logic?

## Scope and evidence

Propose Given–When–Then scenarios before writing test code and obtain the operator's required scenario approval. Start with: valid and invalid rows, a deferred identity and a failing check that must survive into stored quality evidence.

Required observable proof: send valid, flagged and deferred records through the real configured checks and assert stored outcomes and complete row accounting. Reuse existing generic workers, fixtures and harnesses; configuration and invented input data supply source differences. If tooling cannot express a behavior, link a separate capability-gap ticket rather than adding source-specific runtime code here.

Start from skills/data-quality/SKILL.md: plan, measure, decide, write, Publish quality meaning to the business catalog. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Specify generic verification](./05-data-platform-generic-verification.md); [data-profiling: Specify generic verification](./11-data-profiling-generic-verification.md); [data-modeling: Specify generic verification](./17-data-modeling-generic-verification.md); [data-quality: Make progress resumable](./28-data-quality-resume.md)

Priority rationale: Measured checks and dispositions prevent unsafe mappings.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Record distinct Given–When–Then scenarios and obtain the required scenario approval before test implementation.
- [ ] Use the existing generic path to send valid, flagged and deferred records through the real configured checks and assert stored outcomes and complete row accounting.
- [ ] Record stored outcomes, affected checks and limitations; no mock-call-only, static-text or tautological proof.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
