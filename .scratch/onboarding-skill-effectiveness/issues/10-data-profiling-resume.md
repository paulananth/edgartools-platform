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

- [x] Prerequisites 04 and 09 are on current `origin/main`: #1979 and #1980, verified by `git log origin/main` and the prerequisite skill content. (2026-11-20 19:51 ET)
- [x] Specify resume, invalidate and blocked conditions for input fingerprints, profiler version, settings, output locations and whether findings remain applicable. Verified against `profile_data.py`'s `profiled_with` reuse guard and the shared `data-platform/RESUME.md` record; documented in [Resume from the source log](../../../skills/data-profiling/SKILL.md#resume-from-the-source-log). This is an instruction for the session reader, not an automated gate. (2026-11-20 19:51 ET)
- [x] Resume a staged interruption from the recorded artifacts and identify exactly the first unfinished action. Document trace: unchanged artifacts resume at `review findings`; changed pre-approval input reopens at a new `run`; a missing output blocks artifact reuse. No source was run. (2026-11-20 19:51 ET)
- [x] Show changed inputs cannot reuse stale proof and unchanged inputs do not repeat completed work. Verified against the `run` identity comparison and the documented trace; the code path is not exercised by the documentation check. (2026-11-20 19:51 ET)
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [x] Learning → skill: a profiling resume belongs in the source's shared `## Resume` log, carries artifact identity and applicability, and names the first unfinished action; recorded in [Resume from the source log](../../../skills/data-profiling/SKILL.md#resume-from-the-source-log). (2026-11-20 19:51 ET)

## Answer

Resume evidence stays in the source's existing onboarding log under `## Resume`.
The profiling phase entry records mode, input identity, profiler and dependency
versions, settings, output folder and file hashes, applicability, and the next
unchecked action. A matching, intact unapproved profile resumes at that action;
changed input or profiler identity reopens unapproved evidence, missing or
unverifiable artifacts block reuse, and an approved delivery change uses
`compare` against the retained approved baseline. The trace is documented in
[the skill](../../../skills/data-profiling/SKILL.md#resume-from-the-source-log).

Data Modeling owns class, kind and identity decisions; Data Quality owns checks
and row dispositions; Data Onboarding owns the discover step for approved new
datasets. The genericity check validates skill wording and cited paths, not the
resume behavior. Publication remains unchecked because this request explicitly
prohibits commits, pushes and PR creation.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
