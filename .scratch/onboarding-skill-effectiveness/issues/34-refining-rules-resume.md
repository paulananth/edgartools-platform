# refining-rules: Make progress resumable

Type: task
Status: open
Priority: P2
Blocked by: 04, 22, 28, 33
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [refining-rules](../../../skills/refining-rules/SKILL.md)
Step: 4 of 6
Skill dependencies: data-onboarding, data-quality
Applicability: Conditional: the proposed onboarding work changes an existing source or matching policy.

## Question

What evidence allows another session to resume this phase without repeating completed work or trusting stale results?

## Scope and evidence

Use the existing onboarding log or task record as the common progress record, not a new independent state store per skill. Record baseline and candidate digests, changed obligations, carried-forward proof and remaining affected cases. Define when unchanged evidence is reused, invalidated or blocked; retain unfinished work explicitly.

A handoff must identify the next owning skill: data-onboarding only for genuinely new parts; data-operations for execution.

Start from skills/refining-rules/SKILL.md: Shared with Data Onboarding, change-mapping, change-quality, change-matching, check and load. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make progress resumable](./04-data-platform-resume.md); [data-onboarding: Make progress resumable](./22-data-onboarding-resume.md); [data-quality: Make progress resumable](./28-data-quality-resume.md); [refining-rules: Make the entrypoint executable](./33-refining-rules-entrypoint.md)

Priority rationale: Conditional path for existing-source revisions.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Specify resume, invalidate and blocked conditions for baseline and candidate digests, changed obligations, carried-forward proof and remaining affected cases.
- [ ] Resume a staged interruption from the recorded artifacts and identify exactly the first unfinished action.
- [ ] Show changed inputs cannot reuse stale proof and unchanged inputs do not repeat completed work.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
