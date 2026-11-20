# access-audit: Make progress resumable

Type: task
Status: open
Priority: P1
Blocked by: 04, 81
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [access-audit](../../../skills/access-audit/SKILL.md)
Step: 4 of 6
Skill dependencies: data-platform
Applicability: Review the skill or access changes being finalized; run only applicable read-only platform checks.

## Question

What evidence allows another session to resume this phase without repeating completed work or trusting stale results?

## Scope and evidence

Use the existing onboarding log or task record as the common progress record, not a new independent state store per skill. Record audit scope and evidence date, tested objectives, accepted or open findings and pending read-only rechecks. Define when unchanged evidence is reused, invalidated or blocked; retain unfinished work explicitly.

A handoff must identify the next owning skill: the owning operations skill handles authorized remediation, then access-audit rechecks.

Start from skills/access-audit/SKILL.md: Hard stops, Objectives, The gate before finalising a skill role or login. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make progress resumable](./04-data-platform-resume.md); [access-audit: Make the entrypoint executable](./81-access-audit-entrypoint.md)

Priority rationale: Independent access evidence is cross-cutting; remediation is separate.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Specify resume, invalidate and blocked conditions for audit scope and evidence date, tested objectives, accepted or open findings and pending read-only rechecks.
- [ ] Resume a staged interruption from the recorded artifacts and identify exactly the first unfinished action.
- [ ] Show changed inputs cannot reuse stale proof and unchanged inputs do not repeat completed work.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
