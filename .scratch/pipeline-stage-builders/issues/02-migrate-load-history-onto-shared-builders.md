Type: task
Status: ready-for-agent

## Task

Migrate `write_load_history_definition`'s heredoc
(`infra/scripts/deploy-aws-application.sh`) onto the two shared functions
from [Ticket 01](01-build-pipeline-stage-helpers-module.md), replacing all 5
of its existing hand-copied blocks:

- The 3 fundamentals-mode stages (entity-facts, per-filing, thirteenf) via
  `fundamentals_mode_stage(windowed=True, ...)`.
- The ADV-bulk and Firm-Roster force-capable-fetch pairs via
  `force_capable_fetch_stage(...)`.

Add the `sys.path.insert(0, script_dir)` + `from pipeline_stage_helpers
import ...` lines to this heredoc, alongside the existing `mdm_tail_helper`
import already there.

## Acceptance criteria

- [ ] All 5 call sites in `write_load_history_definition` call the shared
      functions instead of hand-built JSON blocks.
- [ ] `tests/architecture/test_load_history_state_machine.py` gains
      byte-identical-output regression assertions for all 5 migrated stages,
      proving this refactor altered no observable behavior — except the
      Force-check `Comment` text, which is deliberately normalized per
      Ticket 01 (assert on that field loosely, or exclude it from the
      equality check, rather than asserting byte-identical `Comment` text).
- [ ] A second `/gof-refactor-reviewer` pass runs against the actual diff
      before commit.
- [ ] Full 3-axis `/code-review` (Standards, Spec, GoF) runs before commit.
- [ ] Full test suite green.

**Blocked by:** [Ticket 01](01-build-pipeline-stage-helpers-module.md).
Independent of [Ticket 03](03-migrate-daily-incremental-onto-shared-builders.md)
— different file, different test file — can run in parallel with it once
Ticket 01 is done.
