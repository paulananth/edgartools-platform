# Bookkeeping stage work

Owner: Codex. Branch: `codex/bookkeeping-stage-work`.
Worktree: `edgartools-platform-bookkeeping-stage-work`.
Base: refreshed `origin/main` `3edde368` plus core PR #732's rebased commit
`43024430`. The open core PR was resynchronized with an explicit remote lease;
the previous head is preserved in `codex/configured-bookkeeping-pre-sync-dd44a01d`.
The dirty shared checkout and other runtime worktrees remain untouched.

Selected next work: remove the flat-worklist limitation before adapting the
remaining warehouse stages. Full legacy migration and AWS cutover remain open.

## Design review

Used the available `gof-refactor-reviewer` before editing `config.py`,
`engine.py`, and `mdm_capabilities.py`; inspected their history and the skill's
smell catalog. History contains the single core implementation commit.
Overall: leave the function registry and existing capability interface in
place. No demonstrated repeated-change cost warrants a pattern hierarchy.
Extend versioned manifest validation and extract one common retained-receipt
verification function used by resume and chained-input resolution.

## Implementation

- Version 2 has explicit worklists for every configured stage, independent
  counts and output references, and prerequisite unit selectors.
- Submission rejects missing/unknown scope, malformed references, forward
  dependencies, absent prerequisite units, and unapproved empty stages.
- Execution resolves only verified outputs, rechecking receipt evidence,
  capability verification, checks and bytes through the full dependency chain.
  The original selector stays frozen in the manifest and work item.
- Version 1 worklist contents/digests and existing operation versions remain
  unchanged; no SQL migration or new table is necessary.
- Final MDM publication checks inspect stage-specific MDM inputs and cannot
  pass while configured work remains incomplete.

## Verification

- Mandatory isolated PostgreSQL 16 control acceptance: **42 passed, no skips**,
  in 99.96 seconds. Includes transform chains with different stage counts,
  bounded continuation, lost acknowledgements, corrupt/missing prerequisite
  evidence, and a real MDM merge with separately configured publication intents.
- Full `tests/unit tests/architecture`: **2,020 passed, eight optional skips,
  27 subtests passed**, in 188.28 seconds. The earlier CLI inventory failures
  are resolved in the complete rerun.
- Targeted Rules files, CLI inventory and Company/GLEIF source regressions:
  **149 passed**. The combined contract and control run before the last MDM
  case passed all 77 tests.
- Wheel build and `git diff --check` passed. No migration changes or updates
  to the canonical empty local control databases were made.

## Next frontier

Integrate source-owned SEC filing worklists and the shared acquisition,
parsing, silver and gold capabilities while migrating existing entry points.
Rules proof evaluator, hosted publication and complete native pipeline
qualification remain necessary. No AWS rollout or old database changes.

MDM dataset registration remains owned by source Rules documents. A platform
document declaring its own MDM dataset contracts currently exports no handoff
receipt and blocks mastering; extending that handoff is an additional remaining
Rules integration task. This slice qualifies source-owned MDM stages and
platform artifact stages, not platform-owned MDM contracts.
