# change-journal: Make progress resumable

Type: task
Status: open
Priority: P1
Blocked by: 04, 46, 51
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [change-journal](../../../skills/change-journal/SKILL.md)
Step: 4 of 6
Skill dependencies: bookkeeping
Applicability: Every source whose processing or publication produces journal events and delivery receipts.

## Question

What evidence allows another session to resume this phase without repeating completed work or trusting stale results?

## Scope and evidence

Use the existing onboarding log or task record as the common progress record, not a new independent state store per skill. Record producer identity, event range, delivery receipts, retry state and applicable processing fingerprints. Define when unchanged evidence is reused, invalidated or blocked; retain unfinished work explicitly.

A handoff must identify the next owning skill: data-operations reports completion; producer and bookkeeping owners recover their own execution.

Start from skills/change-journal/SKILL.md: Skipping and forcing, Required independence, Validate, Recover delivery. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make progress resumable](./04-data-platform-resume.md); [bookkeeping: Make progress resumable](./46-bookkeeping-resume.md); [change-journal: Make the entrypoint executable](./51-change-journal-entrypoint.md)

Priority rationale: Producer completion and delivery evidence must remain distinct.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Specify resume, invalidate and blocked conditions for producer identity, event range, delivery receipts, retry state and applicable processing fingerprints.
- [ ] Resume a staged interruption from the recorded artifacts and identify exactly the first unfinished action.
- [ ] Show changed inputs cannot reuse stale proof and unchanged inputs do not repeat completed work.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
