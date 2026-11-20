# aws-snowflake-operations: Make progress resumable

Type: task
Status: open
Blocked by: 93, 04
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [aws-snowflake-operations](../../../skills/aws-snowflake-operations/SKILL.md)
Step: 4 of 6
Applicability: Conditional: onboarding touches AWS, Snowflake, hosted connections, images or deployment.

## Question

What evidence allows another session to resume this phase without repeating completed work or trusting stale results?

## Scope and evidence

Use the existing onboarding log or task record as the common progress record, not a new independent state store per skill. Record target identity without secrets, committed deployment revision, verified runtime artifact and unresolved infrastructure prerequisites. Define when unchanged evidence is reused, invalidated or blocked; retain unfinished work explicitly.

A handoff must identify the next owning skill: data-operations owns load reconciliation; access-audit owns independent privilege assessment.

Start from skills/aws-snowflake-operations/SKILL.md: Data layers, The hosted MDM store, Pipeline and runtime rules, Image management. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[aws-snowflake-operations: Make the entrypoint executable](./93-aws-snowflake-operations-entrypoint.md); [data-platform: Make progress resumable](./04-data-platform-resume.md)

## Acceptance checklist

- [ ] Specify resume, invalidate and blocked conditions for target identity without secrets, committed deployment revision, verified runtime artifact and unresolved infrastructure prerequisites.
- [ ] Resume a staged interruption from the recorded artifacts and identify exactly the first unfinished action.
- [ ] Show changed inputs cannot reuse stale proof and unchanged inputs do not repeat completed work.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

