Type: task
Status: done

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

## Answer

Migrated (commit `6cfcc688`). All 5 acceptance criteria met. Verified
byte-identical against `main`'s pre-migration output via a direct
JSON-generation comparison (not just unit tests) for all 5 stages — the
only difference anywhere in the generated machine is the deliberate
`FirmRosterForceCheck` Comment normalization. 7 new regression tests added
to `tests/architecture/test_load_history_state_machine.py` (59 total in
that file, all passing). A `/gof-refactor-reviewer` pass on the planned
wiring-in change (before writing the edit) confirmed no orphaned
references among the 12 removed intermediate variables. The full 3-axis
`/code-review` against Ticket 01's closing commit found zero blocking
findings on all three axes — Standards, Spec, and GoF each came back
clean, with only non-blocking notes (a partial-migration data-clump
artifact in the untouched `ecs_state()` closure; a states.update()-vs-
extract-and-rekey idiom inconsistency GoF explicitly said doesn't clear
Rule 0's bar). Full architecture + unit suite green (599 passed, 2
pre-existing skips) before commit.

Ready for [Ticket 03](03-migrate-daily-incremental-onto-shared-builders.md), independent and already unblocked.
