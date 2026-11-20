# openmetadata: Specify generic verification

Type: task
Status: open
Priority: P2
Blocked by: 05, 71, 76
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [openmetadata](../../../skills/openmetadata/SKILL.md)
Step: 5 of 6
Skill dependencies: data-catalog
Applicability: Conditional: OpenMetadata is the configured catalog destination.

## Question

Which complete behavioral scenarios prove this skill's claims, using shared tooling and source-supplied fixtures rather than copied source-specific logic?

## Scope and evidence

Propose Given–When–Then scenarios before writing test code and obtain the operator's required scenario approval. Start with: successful publication, a partial API failure, stale objects and an unchanged second publication.

Required observable proof: publish an invented connected example to the configured local instance, reconcile API readback, recover partial publication and prove metadata actions never start a data load. Reuse existing generic workers, fixtures and harnesses; configuration and invented input data supply source differences. If tooling cannot express a behavior, link a separate capability-gap ticket rather than adding source-specific runtime code here.

Start from skills/openmetadata/SKILL.md: Readback and reconciliation traps, Operator outcome report, Pipeline execution boundary. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

Coordinate with [Move the business-meaning passages out of the openmetadata skill](../../catalog-skill-routing/issues/02-move-business-meaning-out-of-the-openmetadata-skill.md). That ticket remains the owner of its exact text moves; this ticket consumes its result or links any overlap rather than creating a competing implementation.

## Prerequisites

[data-platform: Specify generic verification](./05-data-platform-generic-verification.md); [data-catalog: Specify generic verification](./71-data-catalog-generic-verification.md); [openmetadata: Make progress resumable](./76-openmetadata-resume.md)

Priority rationale: Conditional destination adapter consumes catalog expectations.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Record distinct Given–When–Then scenarios and obtain the required scenario approval before test implementation.
- [ ] Use the existing generic path to publish an invented connected example to the configured local instance, reconcile API readback, recover partial publication and prove metadata actions never start a data load.
- [ ] Record stored outcomes, affected checks and limitations; no mock-call-only, static-text or tautological proof.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
