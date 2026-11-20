# data-profiling: Make progress resumable

Type: task
Status: open
Priority: P0
Blocked by: 04, 09
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-profiling](../../../skills/data-profiling/SKILL.md)
Step: 4 of 6
Skill dependencies: data-platform
Applicability: Every new captured dataset; compare mode only when an approved delivery changes.

## Question

What evidence allows another session to resume this phase without repeating completed work or trusting stale results?

## Scope and evidence

Use the existing onboarding log or task record as the common progress record, not a new independent state store per skill. Record input fingerprints, profiler version, settings, output locations and whether findings remain applicable. Define when unchanged evidence is reused, invalidated or blocked; retain unfinished work explicitly.

A handoff must identify the next owning skill: data-modeling, data-quality and data-onboarding.

Start from skills/data-profiling/SKILL.md: Modes, Profile once, How to work, Compare a new delivery. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make progress resumable](./04-data-platform-resume.md); [data-profiling: Make the entrypoint executable](./09-data-profiling-entrypoint.md)

Priority rationale: Reusable evidence is the input to every source model.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Specify resume, invalidate and blocked conditions for input fingerprints, profiler version, settings, output locations and whether findings remain applicable.
- [ ] Resume a staged interruption from the recorded artifacts and identify exactly the first unfinished action.
- [ ] Show changed inputs cannot reuse stale proof and unchanged inputs do not repeat completed work.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
