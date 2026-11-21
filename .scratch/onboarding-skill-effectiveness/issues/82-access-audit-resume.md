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

- [x] Specify resume, invalidate and blocked conditions for audit scope and evidence date, tested objectives, accepted or open findings and pending read-only rechecks. Verified by review of [Resume an audit](../../../skills/access-audit/SKILL.md#resume-an-audit): it defines the common task record, recorded fields, review-window reuse, scope/revision invalidation, missing/stale-evidence blocks, accepted/open finding records and the remediation-to-recheck handoff. (2026-11-20 20:10 ET)
- [x] Resume a staged interruption from the recorded artifacts and identify exactly the first unfinished action. Verified by the staged-interruption example in [Resume an audit](../../../skills/access-audit/SKILL.md#examples-staged-interruption): the first action is Data Operations' authorized remediation; after it records completion, access-audit performs the pending CST read-only recheck. This is a documented walkthrough, not an execution test. (2026-11-20 20:10 ET)
- [x] Show changed inputs cannot reuse stale proof and unchanged inputs do not repeat completed work. Verified by reviewing the reuse/invalidate/block rules and both changed-setting and unchanged-input branches in the staged-interruption example. This demonstrates the written procedure only; no runtime enforcer or behavior test was added. (2026-11-20 20:10 ET)
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [x] Learning → skill: a resume record keeps audit scope, dated evidence, completed objectives and pending owner handoffs together; unchanged in-window results are reused, changed scope or logic reopens affected results, and stale or incomplete evidence blocks. Recorded and verified in [Resume an audit](../../../skills/access-audit/SKILL.md#resume-an-audit). (2026-11-20 20:10 ET)

## Answer

Another session resumes an audit from the `## Resume` section of the existing onboarding log or task record. The record names
the scope, assessed objectives, evidence date and revision, artifact paths and hashes, result and finding status, owners, and
pending read-only rechecks. Results are reused only for unchanged scope and inputs within the task's recorded review window;
changed principals, settings or audit logic reopen affected results. Missing, mismatched or out-of-window evidence blocks
resumption. The owning operations skill handles authorized remediation, then access-audit performs the pending recheck.

## Changes

- `skills/access-audit/SKILL.md`: added **Resume an audit** with reuse, invalidation, blocked and handoff rules, plus a staged
  interruption example. No scenario or test code was added. The skill is 209 lines, below the 500-line limit.
- No installed `access-audit` copy exists at `~/.agents/skills/access-audit`. The installed `data-platform` link points to
  `/Users/aneenaananth/.local/share/edgartools/skill-source/skills/data-platform`, which is absent, so that copy could not be
  compared. The installed `write-skill` guidance was read through its `~/.agents/skills/write-skill/SKILL.md` symlink to the
  gstack installation; its header identifies it as generated from `SKILL.md.tmpl`. No installed skill was modified.

## Trace

The staged interruption example is a document walkthrough, not a live audit or behavior test. It starts with CHG and IND
complete, CST failed and handed to Data Operations, and the CST recheck unchecked. With unchanged in-window evidence, the first
unfinished action is Data Operations' authorized remediation. After that owner records completion, access-audit rechecks CST
read-only. A changed setting or adapter revision reopens affected proof; a missing or expired artifact blocks the resume.

Prerequisites were checked against hosted `main` using `gh`: it is `c1826fbcc3a66a6beb08947d9089fbb4889af4a0`. GitHub's
compare endpoint reports both ticket 04's `4881e8322909888860db576f65730bc4889dc5a4` (#1979) and ticket 81's
`f8ec7071b8891855758f05ffd71bae0a38af1284` (#1977) as ancestors of `main`. Their ticket files were not edited.

## Validation

- `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider tests/unit/test_profiling_genericity.py tests/unit/test_guides_name_existing_paths.py`: **144 passed**. This checks documentation genericity and referenced paths; it does not exercise audit behavior or resumption.
- `git diff --check`: clean.
- `wc -l skills/access-audit/SKILL.md`: **209 lines**, under 500.
- `gh api repos/paulananth/edgartools-platform/commits/main` and the two `compare/<prerequisite>...main` reads: hosted main head and both prerequisite ancestries verified.
- Not run: a live access audit or behavior test. The change is skill documentation, and the staged interruption was intentionally documented rather than implemented as scenario/test code.

## Completion evidence

Publication remains unchecked because this session's instruction explicitly prohibits committing, pushing or creating a PR. The
ticket stays open until that publication and its remaining required review evidence are complete.

Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition,
not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
