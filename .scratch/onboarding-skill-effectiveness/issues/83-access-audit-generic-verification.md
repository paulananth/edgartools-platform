# access-audit: Specify generic verification

Type: task
Status: open
Priority: P1
Blocked by: 05, 82
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [access-audit](../../../skills/access-audit/SKILL.md)
Step: 5 of 6
Skill dependencies: data-platform
Applicability: Review the skill or access changes being finalized; run only applicable read-only platform checks.

## Question

Which complete behavioral scenarios prove this skill's claims, using shared tooling and source-supplied fixtures rather than copied source-specific logic?

## Scope and evidence

Propose Given–When–Then scenarios before writing test code and obtain the operator's required scenario approval. Start with: a restricted runtime role, a denied audit view and an overprivileged role detected without mutation.

Required observable proof: use a generic disposable-store role scenario to distinguish PASS, FAIL and NOT_TESTED while proving the audit performs no remediation. Reuse existing generic workers, fixtures and harnesses; configuration and invented input data supply source differences. If tooling cannot express a behavior, link a separate capability-gap ticket rather than adding source-specific runtime code here.

Start from skills/access-audit/SKILL.md: Hard stops, Objectives, The gate before finalising a skill role or login. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Specify generic verification](./05-data-platform-generic-verification.md); [access-audit: Make progress resumable](./82-access-audit-resume.md)

Priority rationale: Independent access evidence is cross-cutting; remediation is separate.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Record distinct Given–When–Then scenarios and obtain the required scenario approval before test implementation.
- [ ] Use the existing generic path to use a generic disposable-store role scenario to distinguish PASS, FAIL and NOT_TESTED while proving the audit performs no remediation.
- [ ] Record stored outcomes, affected checks and limitations; no mock-call-only, static-text or tautological proof.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
