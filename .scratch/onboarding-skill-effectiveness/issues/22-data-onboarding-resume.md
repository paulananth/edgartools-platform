# data-onboarding: Make progress resumable

Type: task
Status: open
Blocked by: 21, 04
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-onboarding](../../../skills/data-onboarding/SKILL.md)
Step: 4 of 6
Applicability: Every new source or new kind; live-source revisions route to refining-rules.

## Question

What evidence allows another session to resume this phase without repeating completed work or trusting stale results?

## Scope and evidence

Use the existing onboarding log or task record as the common progress record, not a new independent state store per skill. Record each part's model, rules digest, generated artifacts, completed checks, missing inputs and next owning skill. Define when unchanged evidence is reused, invalidated or blocked; retain unfinished work explicitly.

A handoff must identify the next owning skill: bookkeeping for execution and data-operations for the local proof and operational handoff.

Start from skills/data-onboarding/SKILL.md: Modes in order, The files are the rules, metadata, check and load; MAP.md and TARGETS.md. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

The prior split is recorded in [The data-onboarding skill is split behind pointers](../../rebuild-priorities/issues/215-split-the-data-onboarding-skill.md); inspect current references before repeating it.

## Prerequisites

[data-onboarding: Make the entrypoint executable](./21-data-onboarding-entrypoint.md); [data-platform: Make progress resumable](./04-data-platform-resume.md)

## Acceptance checklist

- [ ] Specify resume, invalidate and blocked conditions for each part's model, rules digest, generated artifacts, completed checks, missing inputs and next owning skill.
- [ ] Resume a staged interruption from the recorded artifacts and identify exactly the first unfinished action.
- [ ] Show changed inputs cannot reuse stale proof and unchanged inputs do not repeat completed work.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

