Type: task
Status: done

## Task

Migrate `write_warehouse_mdm_gold_definition`'s heredoc
(`infra/scripts/deploy-aws-application.sh`, builds `daily_incremental`) onto
`force_capable_fetch_stage` from [Ticket 01](01-build-pipeline-stage-helpers-module.md),
replacing its 2 existing hand-copied instances (ADV-bulk and Firm-Roster) —
the second hand-copy of this shape, whose own code comment today admits it
is "kept in sync per this file's documented ... duplication convention"
rather than genuinely shared.

Add the `sys.path.insert(0, script_dir)` + `from pipeline_stage_helpers
import ...` lines to this heredoc, alongside the existing `mdm_tail_helper`
import already there.

`daily_incremental` has no fundamentals-mode stages yet — wiring those in is
explicitly out of scope for this map (see map.md); `fundamentals_mode_stage`
is proven by Ticket 02 against `load_history` only.

## Acceptance criteria

- [ ] Both call sites in `write_warehouse_mdm_gold_definition` call
      `force_capable_fetch_stage` instead of hand-built JSON blocks.
- [ ] `tests/architecture/test_daily_incremental_state_machine.py` gains
      byte-identical-output regression assertions for both migrated stages
      (same `Comment`-text exception as Ticket 02).
- [ ] A second `/gof-refactor-reviewer` pass runs against the actual diff
      before commit.
- [ ] Full 3-axis `/code-review` (Standards, Spec, GoF) runs before commit.
- [ ] Full test suite green.

**Blocked by:** [Ticket 01](01-build-pipeline-stage-helpers-module.md).
Independent of [Ticket 02](02-migrate-load-history-onto-shared-builders.md)
— different file, different test file — can run in parallel with it once
Ticket 01 is done.

## Answer

Migrated (commit `74c2ac44`). All 5 acceptance criteria met. Verified
byte-identical against `main`'s pre-migration output for both trios (direct
JSON comparison) — the only difference anywhere is the same
`FirmRosterForceCheck` Comment normalization Ticket 02 already applied to
`load_history`'s copy. The stale "kept in sync ... manually" comment was
updated, not left misleading, to reflect that both copies now share the
same function. 3 new regression tests added to
`tests/architecture/test_daily_incremental_state_machine.py` (30 total in
that file, all passing). A `/gof-refactor-reviewer` pass on the planned
wiring-in change confirmed no orphaned references. The full 3-axis
`/code-review` against Ticket 02's closing commit found zero blocking
findings on all three axes (GoF explicitly reported zero rather than
manufacturing any). Full architecture + unit suite green (602 passed, 2
pre-existing skips) before commit.

This closes the pipeline-stage-builders map — all 3 tickets done, both
hand-copied duplication axes (windowed fundamentals-mode stage,
force-capable fetch trio) are now fully collapsed onto the two shared
functions across both pipelines.
