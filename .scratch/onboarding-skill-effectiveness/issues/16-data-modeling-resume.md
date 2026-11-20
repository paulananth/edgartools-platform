# data-modeling: Make progress resumable

Type: task
Status: open
Priority: P0
Blocked by: 04, 10, 15
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-modeling](../../../skills/data-modeling/SKILL.md)
Step: 4 of 6
Skill dependencies: data-profiling
Applicability: Every new part whose class, identity, relationship or destination needs mapping.

## Question

What evidence allows another session to resume this phase without repeating completed work or trusting stale results?

## Scope and evidence

Use the existing onboarding log or task record as the common progress record, not a new independent state store per skill. Record part decisions, supporting findings, unresolved semantics and downstream contracts affected. Define when unchanged evidence is reused, invalidated or blocked; retain unfinished work explicitly.

A handoff must identify the next owning skill: data-onboarding and data-quality; data-catalog consumes the resulting meaning.

Start from skills/data-modeling/SKILL.md: Decision rules, Workflow, Prove the model on the data before building. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make progress resumable](./04-data-platform-resume.md); [data-profiling: Make progress resumable](./10-data-profiling-resume.md); [data-modeling: Make the entrypoint executable](./15-data-modeling-entrypoint.md)

Priority rationale: Identity and destination decisions precede configuration.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Specify resume, invalidate and blocked conditions for part decisions, supporting findings, unresolved semantics and downstream contracts affected.
- [ ] Resume a staged interruption from the recorded artifacts and identify exactly the first unfinished action.
- [ ] Show changed inputs cannot reuse stale proof and unchanged inputs do not repeat completed work.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
