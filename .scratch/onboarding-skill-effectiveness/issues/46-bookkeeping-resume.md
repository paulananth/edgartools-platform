# bookkeeping: Make progress resumable

Type: task
Status: open
Priority: P1
Blocked by: 04, 22, 45
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [bookkeeping](../../../skills/bookkeeping/SKILL.md)
Step: 4 of 6
Skill dependencies: data-onboarding
Applicability: Every source's declared execution targets; honor the target's configured grain.

## Question

What evidence allows another session to resume this phase without repeating completed work or trusting stale results?

## Scope and evidence

Use the existing onboarding log or task record as the common progress record, not a new independent state store per skill. Record run identity, pinned inputs, verified versus unfinished steps, checkpoints and failure reason. Define when unchanged evidence is reused, invalidated or blocked; retain unfinished work explicitly.

A handoff must identify the next owning skill: data-operations operates the run; change-journal owns delivery receipts.

Start from skills/bookkeeping/SKILL.md: Required independence, Source registration, Grain, Validate, Recover. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make progress resumable](./04-data-platform-resume.md); [data-onboarding: Make progress resumable](./22-data-onboarding-resume.md); [bookkeeping: Make the entrypoint executable](./45-bookkeeping-entrypoint.md)

Priority rationale: Configured targets must execute with verified recovery.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Specify resume, invalidate and blocked conditions for run identity, pinned inputs, verified versus unfinished steps, checkpoints and failure reason.
- [ ] Resume a staged interruption from the recorded artifacts and identify exactly the first unfinished action.
- [ ] Show changed inputs cannot reuse stale proof and unchanged inputs do not repeat completed work.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
