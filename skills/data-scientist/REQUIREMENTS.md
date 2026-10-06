# Data scientist requirements

Decided from [the runtime account](../../docs/research/claude-codex-runtimes-2026-10-06.md), [data-profiling](../data-profiling/SKILL.md), [data-quality](../data-quality/SKILL.md), and `CONTEXT.md`. This note is the boundary. The skill that follows it does not add a second one.

## Scope

The data scientist studies captured data and mastered outcomes and reports the evidence.

In scope:

- A question with a measurable answer: what a data set contains, whether a new delivery drifted, how many records a check fires on, or what MDM currently holds.
- Reading `REPORT.md` and `findings.yaml`, including the tests, the counts, and the unknowns data-profiling already recorded.
- A comparison of a new delivery, by data-profiling's compare mode. The drift list is the evidence. This skill does not turn drift into a rule change.
- A count of checks on records, by data-quality's measure mode. The count is the evidence. Choosing `on_fail` stays with the operator, through data-quality.
- A read of mastered entities, and of one run's recorded state, through commands that only select. The run read is `bookkeeping status`. It returns item states and the checks already stored on those items. `bookkeeping checks` is not a read: it freezes the run and can mark the run blocked. That command stays with bookkeeping.

Out of scope: deciding a kind or a relationship type (data-modeling); moving a run forward (bookkeeping); writing `quality.yaml`, `source.yaml`, or a merge rule; approving findings; switching a matching rule on.

## Use when

Use when the operator asks what a data set shows, whether a new delivery drifted, how many records a check fires on, or for a report that keeps the evidence next to each claim.

Do not use it to onboard a feed, to resume a run, or to approve a model of identity.

## Refusals

- Do not approve findings, a check, or a matching rule, and do not record words the operator did not say.
- Do not write `quality.yaml` or any rules file.
- Do not invent a command that fits a model or runs a hypothesis test. No such command exists.
- Do not print a raw personal value. Profiling already masks those samples to their shape.
- Do not replace an unknown with a guess. One delivery cannot show that a key persisted. Say unknown.
- Do not treat similar names as one entity. `CONTEXT.md` forbids that.
- Do not edit Claude-owned or Codex-owned paths, and do not request anything from `sec.gov`.
- Do not run a bookkeeping command that freezes a run or can mark it blocked. Hand the run to bookkeeping.

## Open questions

1. Nothing on the `edgar-warehouse` command line fits a statistical model. The measurements this skill may use are data-profiling, data-quality's measure mode, and the read-only commands named in the skill. A result that would change who matches whom goes to [refining-rules](../refining-rules/SKILL.md), which requires a measured proof the operator approves. This skill does not write `rules/merge/pending-proofs.yaml`.
2. Name matching is not a method on `main`. Claude's trial is uncommitted on `claude/profiling-07b-name-matching` in another worktree. Do not apply it.
3. Data-profiling compare leaves key persistence unknown when only one delivery exists. Report that unknown. Do not impute the missing delivery.
4. Whether a measured difference should change a live rule is the operator's decision. The handoff is refining-rules or data-quality. It is not a silent edit.
