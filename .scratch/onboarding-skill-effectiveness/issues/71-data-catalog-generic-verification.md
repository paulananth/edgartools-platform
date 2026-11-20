# data-catalog: Specify generic verification

Type: task
Status: open
Priority: P1
Blocked by: 05, 23, 29, 65, 70
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-catalog](../../../skills/data-catalog/SKILL.md)
Step: 5 of 6
Skill dependencies: data-governance, data-onboarding, data-quality
Applicability: Every source's business metadata and steward-facing publication.

## Question

Which complete behavioral scenarios prove this skill's claims, using shared tooling and source-supplied fixtures rather than copied source-specific logic?

## Scope and evidence

Propose Given–When–Then scenarios before writing test code and obtain the operator's required scenario approval. Start with: a source spanning multiple domains, a relationship asset and a quality definition published to one catalog.

Required observable proof: compare intended domains, glossary associations, quality meaning and lineage with destination readback rather than HTTP acknowledgments. Reuse existing generic workers, fixtures and harnesses; configuration and invented input data supply source differences. If tooling cannot express a behavior, link a separate capability-gap ticket rather than adding source-specific runtime code here.

Start from skills/data-catalog/SKILL.md: Use the skill that owns the decision, Choose the catalog's own skill, Report publication as separate outcomes. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

Coordinate with [Move the business-meaning passages out of the openmetadata skill](../../catalog-skill-routing/issues/02-move-business-meaning-out-of-the-openmetadata-skill.md). That ticket remains the owner of its exact text moves; this ticket consumes its result or links any overlap rather than creating a competing implementation.

## Prerequisites

[data-platform: Specify generic verification](./05-data-platform-generic-verification.md); [data-onboarding: Specify generic verification](./23-data-onboarding-generic-verification.md); [data-quality: Specify generic verification](./29-data-quality-generic-verification.md); [data-governance: Specify generic verification](./65-data-governance-generic-verification.md); [data-catalog: Make progress resumable](./70-data-catalog-resume.md)

Priority rationale: Business metadata consumes the model, targets and checks.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Record distinct Given–When–Then scenarios and obtain the required scenario approval before test implementation.
- [ ] Use the existing generic path to compare intended domains, glossary associations, quality meaning and lineage with destination readback rather than HTTP acknowledgments.
- [ ] Record stored outcomes, affected checks and limitations; no mock-call-only, static-text or tautological proof.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
