# Live discovery narration

Operator request: make data-profiling and data-onboarding continuously explain
their investigation in the conversation, so the operator can follow the
discovery as it happens.

## Checklist

- [x] Inspect current skills, main and other runtimes' changes before editing. Verified against fetched main `dfc08e77`, worktree status and open PR list; protected checkout unchanged (2026-10-09 17:18 ET).
- [x] Require evidence-based discovery updates in data-profiling, including long-running commands and unknown findings. Reviewed the new opening section against the operator's request (2026-10-09 17:18 ET).
- [x] Require live updates across data-onboarding phases and its delegated profiling work. Reviewed mandatory link to profiling's narration contract and onboarding-specific phase/evidence updates (2026-10-09 17:18 ET).
- [x] Validate skill structure and walk through fast discovery, silent scan, failed command and approval pause scenarios. Both skill-creator validators and `git diff --check` pass; manual scenario review below (2026-10-09 17:18 ET).
- [x] Add an operator coordination note in both skills protecting the narration requirements from stale LLM edits. Reviewed both notes and reran both skill validators successfully (2026-10-09 17:20 ET).
- [ ] Review the diff, run the overlap guard, commit and publish a reviewable PR.

## Scope

Instruction changes only. Preserve existing profiling algorithms, data privacy,
local-input restrictions, evidence requirements and operator approval gates.

## Verification

Manual instruction walkthrough; this is a review of required behavior, not a
claim that an independent agent or a new data scan executed it.

| Scenario | Required observable behavior in the changed skills |
| --- | --- |
| Fast discovery reveals a duplicate key | Explain measured duplication, its consequence for the key, and the next composite-key check immediately. |
| A full scan emits no output for several minutes | Yield the command; check it at most every 30 seconds; give elapsed time and the running stage at least every 60 seconds without inventing counts or an ETA. |
| Original input format is refused but an export profiles | Explain exploratory evidence and the remaining original-reader gap; identify the next reconciliation check. |
| Evidence disproves an earlier hypothesis | Explicitly explain the changed conclusion and the evidence that changed it. |
| Mapping or activation needs approval | Summarize evidence, unresolved questions and recommendation; preserve the operator's approval gate and exact words. |

The onboarding link resolves to the profiling section. Existing frontmatter,
local-input restrictions and approval rules are retained. No profiling code,
rules, stores or datasets are changed.

## Ownership

Guard run after editing: exit 1 for only `skills/data-onboarding/SKILL.md` in
`grok/name-frequency`. Its three source-extract terminology edits are already
present on main; the worktree is otherwise clean for this file. Our added
section is separate. The operator authorized committing and publishing this
change: "make a note to other llms not to over write the skills, now commit
create pr". This resolves the previously reported onboarding-file overlap;
Grok's worktree is untouched. Any newly reported overlap needs its own review.
