# mdm-engineering: Make progress resumable

Type: task
Status: open
Priority: P2
Blocked by: 04, 16, 39
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [mdm-engineering](../../../skills/mdm-engineering/SKILL.md)
Step: 4 of 6
Skill dependencies: data-modeling
Applicability: Conditional: choose mastering proof or investigate a demonstrated engine or storage gap; configuration remains the default.

## Question

What evidence allows another session to resume this phase without repeating completed work or trusting stale results?

## Scope and evidence

Use the existing onboarding log or task record as the common progress record, not a new independent state store per skill. Record claim, affected policy and engine revisions, proof cohort, store identity and remaining unproved branches. Define when unchanged evidence is reused, invalidated or blocked; retain unfinished work explicitly.

A handoff must identify the next owning skill: data-onboarding or refining-rules when configuration suffices; separate implementation work for a real gap.

Start from skills/mdm-engineering/SKILL.md: Hard stops, Choose the cheapest proof, Independent installed qualification. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make progress resumable](./04-data-platform-resume.md); [data-modeling: Make progress resumable](./16-data-modeling-resume.md); [mdm-engineering: Make the entrypoint executable](./39-mdm-engineering-entrypoint.md)

Priority rationale: Conditional mastering proof or demonstrated engine gap.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Specify resume, invalidate and blocked conditions for claim, affected policy and engine revisions, proof cohort, store identity and remaining unproved branches.
- [ ] Resume a staged interruption from the recorded artifacts and identify exactly the first unfinished action.
- [ ] Show changed inputs cannot reuse stale proof and unchanged inputs do not repeat completed work.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
