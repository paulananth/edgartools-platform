# aws-snowflake-operations: Specify generic verification

Type: task
Status: open
Priority: P3
Blocked by: 05, 59, 83, 94
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [aws-snowflake-operations](../../../skills/aws-snowflake-operations/SKILL.md)
Step: 5 of 6
Skill dependencies: data-operations, access-audit
Applicability: Conditional: onboarding touches AWS, Snowflake, hosted connections, images or deployment.

## Question

Which complete behavioral scenarios prove this skill's claims, using shared tooling and source-supplied fixtures rather than copied source-specific logic?

## Scope and evidence

Propose Given–When–Then scenarios before writing test code and obtain the operator's required scenario approval. Start with: an absent hosted prerequisite, a stale deployed image and a deployment blocked before local qualification.

Required observable proof: validate plans and runtime identity through existing generic tooling and independently read back the selected target; do not deploy merely to evaluate documentation. Reuse existing generic workers, fixtures and harnesses; configuration and invented input data supply source differences. If tooling cannot express a behavior, link a separate capability-gap ticket rather than adding source-specific runtime code here.

Start from skills/aws-snowflake-operations/SKILL.md: Data layers, The hosted MDM store, Pipeline and runtime rules, Image management. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Specify generic verification](./05-data-platform-generic-verification.md); [data-operations: Specify generic verification](./59-data-operations-generic-verification.md); [access-audit: Specify generic verification](./83-access-audit-generic-verification.md); [aws-snowflake-operations: Make progress resumable](./94-aws-snowflake-operations-resume.md)

Priority rationale: Hosted expansion follows local qualification and access evidence.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Record distinct Given–When–Then scenarios and obtain the required scenario approval before test implementation.
- [ ] Use the existing generic path to validate plans and runtime identity through existing generic tooling and independently read back the selected target; do not deploy merely to evaluate documentation.
- [ ] Record stored outcomes, affected checks and limitations; no mock-call-only, static-text or tautological proof.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
