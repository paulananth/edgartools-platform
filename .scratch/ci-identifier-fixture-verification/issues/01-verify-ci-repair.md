# Verify the identifier fixture CI repair

Status: complete for CI verification. The operator asked to fix CI while shared engine/adapter
work remains scoped separately. Another runtime merged PR #1087 at `b8e388f9`
as this diagnosis began. Preserve its implementation; verify the actual fix.

This is historical verification of main `dcba6d03` at 2026-10-18 14:13 ET,
not a permanent claim about the checks on a later main revision.

## Checklist

- [x] Retrieve failed Unit job from CI run `39151650577` and verify the same root failure on main run `39150785542`: five identifier fixture setup errors before cleanup — 2026-10-18 14:02 ET.
- [x] Reproduce `tests/unit/test_rules_approve_rule.py` on failing main `a115c725`: four passed, five setup errors in 1.55 seconds — 2026-10-18 14:02 ET.
- [x] Verify merged #1087 (`b8e388f9`) on the same test file: nine passed in 2.17 seconds; fixture assertions remain, checked after setup — 2026-10-18 14:02 ET.
- [x] Observe current main `dcba6d03`, run `39152692286`: all nine required checks passed, including Unit, MDM, Engine, PostgreSQL integration, all three adapter jobs, shell lint and aggregate gate. Independently recheck unchanged main head; watcher exited successfully — 2026-10-18 14:13 ET.
- [x] Record Standards, Spec and GoF review, before/after evidence and the separately pending engine/adapter task below — 2026-10-18 14:13 ET.
- [x] Learning → skill: none. No skill defect found. MDM engineering's cheapest-proof instruction already requires affected tests and CI; the merged repair also recorded the moving-main integration lesson in repository instructions — 2026-10-18 14:13 ET.

## Root cause and already-merged repair

The test fixture copied the current rules and asserted an identifier matching
rule was inactive before removing that rule to prepare its own test input.
Two independently green PRs introduced the test and switched on the rule;
their combined main state therefore failed before any test behavior ran.

#1087 moves the setup assertion after removing the live activation/stamp,
retaining the assertion. Its repeated-approval test removes the final comment
block added by that test instead of truncating at an older matching comment.
No activation requirement, runtime behavior or test acceptance assertion was
relaxed. Another runtime authored and merged the repair; this ticket adds no
duplicate runtime/test fix.

CI on `b8e388f9` passed Unit, MDM, shell lint and all three adapter jobs before
the run was cancelled by a subsequent main merge. Runs on `956a8a83` and
`8b6613b0` were also superseded. Current main `dcba6d03` retains #1087, and its
replacement run `39152692286` passed all nine checks before the hard deadline
of 2026-10-18 14:16 ET. The watcher tracked replaced heads and exited on the
verified all-green current main. Its replaced processes were also verified
stopped. Verification ran from the first recorded check at 14:00 ET to final
CI confirmation at 14:13 ET: thirteen minutes including cancelled/restarted
runs. The long-wait expectation and deadline were reported during execution.

Final CI: https://github.com/paulananth/edgartools-platform/actions/runs/39152692286

Private local logs: `/tmp/ci-identifier-fixture-before.log` and
`/tmp/ci-identifier-fixture-after.log`. The failed-job log and bounded watcher
are also retained outside the repository.

## Standards

Dedicated fresh Codex worktree; main and other runtimes' WIP untouched. The
merged fix is inspected and tested, not reimplemented or committed on another
runtime's branch. Targeted tests use separate worktree/testmon caches and each
completed within five minutes. No runtime migration, source activation or
operator approval occurred. No test container was required for these tests.

## Spec

The actual failing tests were reproduced and the existing merged repair
passes them. No engine/adapter change or new implementation is introduced by
this CI verification. Full current-main CI passed all nine checks. The
Company three-engine integration task retains the operator's separate scope:
fix the existing shared engine and existing skill-owned adapter only.

## GoF

`gof-refactor-reviewer` is available and its code/history method was used on
the same failing/fixed fixture diff. Verdict: retain the existing design.
The cause is a postcondition checked before setup plus truncation at an older
comment. Fixing those statements preserves the test design; a pattern, helper
hierarchy or runtime refactor would add cost without addressing another need.
