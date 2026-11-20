# openmetadata: Make the entrypoint executable

Type: task
Status: open
Priority: P2
Blocked by: 03, 69, 74
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [openmetadata](../../../skills/openmetadata/SKILL.md)
Step: 3 of 6
Skill dependencies: data-catalog
Applicability: Conditional: OpenMetadata is the configured catalog destination.

## Question

What is the shortest sufficient entrypoint for a reader to perform this phase correctly using existing supported commands?

## Scope and evidence

Keep the entrypoint focused on applicability, prerequisites, exact supported commands, expected outputs, next owner and stop conditions. Inputs: the business catalog contract, configured instance and private credential-variable names. Outputs: published native objects, readback reconciliation and separate status for each publication family. Open optional references only when needed; do not move a hard stop out of the required reading path.

Check existing splits before proposing another move; line count alone is not a completion measure.

Start from skills/openmetadata/SKILL.md: Readback and reconciliation traps, Operator outcome report, Pipeline execution boundary. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

Coordinate with [Move the business-meaning passages out of the openmetadata skill](../../catalog-skill-routing/issues/02-move-business-meaning-out-of-the-openmetadata-skill.md). That ticket remains the owner of its exact text moves; this ticket consumes its result or links any overlap rather than creating a competing implementation.

## Prerequisites

[data-platform: Make the entrypoint executable](./03-data-platform-entrypoint.md); [data-catalog: Make the entrypoint executable](./69-data-catalog-entrypoint.md); [openmetadata: Reconcile shared rules](./74-openmetadata-consistent-rules.md)

Priority rationale: Conditional destination adapter consumes catalog expectations.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Produce an entrypoint that consumes the business catalog contract, configured instance and private credential-variable names and yields published native objects, readback reconciliation and separate status for each publication family.
- [ ] Verify referenced paths and supported commands; retain mandatory stops and discoverability of optional detail.
- [ ] Walk one applicable example to its handoff without loading unrelated references or repeating another skill's procedure.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
