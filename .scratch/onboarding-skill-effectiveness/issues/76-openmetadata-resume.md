# openmetadata: Make progress resumable

Type: task
Status: open
Priority: P2
Blocked by: 04, 70, 75
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [openmetadata](../../../skills/openmetadata/SKILL.md)
Step: 4 of 6
Skill dependencies: data-catalog
Applicability: Conditional: OpenMetadata is the configured catalog destination.

## Question

What evidence allows another session to resume this phase without repeating completed work or trusting stale results?

## Scope and evidence

Use the existing onboarding log or task record as the common progress record, not a new independent state store per skill. Record configured destination identity, expected object inventory, published revisions and unresolved readback differences. Define when unchanged evidence is reused, invalidated or blocked; retain unfinished work explicitly.

A handoff must identify the next owning skill: data-catalog judges semantic completeness; data-operations owns source execution.

Start from skills/openmetadata/SKILL.md: Readback and reconciliation traps, Operator outcome report, Pipeline execution boundary. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

Coordinate with [Move the business-meaning passages out of the openmetadata skill](../../catalog-skill-routing/issues/02-move-business-meaning-out-of-the-openmetadata-skill.md). That ticket remains the owner of its exact text moves; this ticket consumes its result or links any overlap rather than creating a competing implementation.

## Prerequisites

[data-platform: Make progress resumable](./04-data-platform-resume.md); [data-catalog: Make progress resumable](./70-data-catalog-resume.md); [openmetadata: Make the entrypoint executable](./75-openmetadata-entrypoint.md)

Priority rationale: Conditional destination adapter consumes catalog expectations.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Specify resume, invalidate and blocked conditions for configured destination identity, expected object inventory, published revisions and unresolved readback differences.
- [ ] Resume a staged interruption from the recorded artifacts and identify exactly the first unfinished action.
- [ ] Show changed inputs cannot reuse stale proof and unchanged inputs do not repeat completed work.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
