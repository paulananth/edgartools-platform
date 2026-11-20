# data-operations: Make progress resumable

Type: task
Status: open
Priority: P1
Blocked by: 04, 22, 46, 52, 57
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-operations](../../../skills/data-operations/SKILL.md)
Step: 4 of 6
Skill dependencies: data-onboarding, bookkeeping, change-journal
Applicability: Every local source qualification and operational load; hosted actions require applicable authorization.

## Question

What evidence allows another session to resume this phase without repeating completed work or trusting stale results?

## Scope and evidence

Use the existing onboarding log or task record as the common progress record, not a new independent state store per skill. Record store generation, run and capture references, rules version, verified row counts and the next unfinished operation. Define when unchanged evidence is reused, invalidated or blocked; retain unfinished work explicitly.

A handoff must identify the next owning skill: bookkeeping and change-journal for recovery; catalog publication follows verified outcomes.

Start from skills/data-operations/SKILL.md: Start with live state, Install and enable one source, Load a capture, Operate the recurring loop. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make progress resumable](./04-data-platform-resume.md); [data-onboarding: Make progress resumable](./22-data-onboarding-resume.md); [bookkeeping: Make progress resumable](./46-bookkeeping-resume.md); [change-journal: Make progress resumable](./52-change-journal-resume.md); [data-operations: Make the entrypoint executable](./57-data-operations-entrypoint.md)

Priority rationale: Local load reconciliation completes operational qualification.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Specify resume, invalidate and blocked conditions for store generation, run and capture references, rules version, verified row counts and the next unfinished operation.
- [ ] Resume a staged interruption from the recorded artifacts and identify exactly the first unfinished action.
- [ ] Show changed inputs cannot reuse stale proof and unchanged inputs do not repeat completed work.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
