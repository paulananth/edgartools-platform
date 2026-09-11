Type: task
Status: open

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
