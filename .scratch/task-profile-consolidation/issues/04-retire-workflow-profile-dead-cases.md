# 04 — Retire workflow_profile()'s dead/superseded cases

**What to build:** With tickets 02 and 03 landed, every real caller resolves
task profile through the ticket 01 shared mapping. `workflow_profile()`
(`infra/scripts/deploy-aws-application.sh`, ~lines 1332–1358) is now either
fully dead or entirely redundant with the shared mapping. Delete it, or
reduce it to a thin pass-through over the shared mapping if any caller still
needs the `workflow_profile()` name/signature for now — either way, there
must be exactly one place task-profile resolution logic actually lives, with
no independent case statement able to silently drift from what callers do
(the failure mode that caused the original incidents).

**Blocked by:** 02, 03

**Status:** resolved (2026-08-19)

- [x] `workflow_profile()`'s case statement no longer contains independent
      profile-resolution logic — it's deleted, or it's a direct pass-through
      to the ticket 01 shared mapping
- [x] No remaining caller resolves a task profile any way other than through
      the ticket 01 shared mapping
- [x] `grep` confirms no other reference to the old dead `daily_incremental`/
      `bootstrap` cases remains anywhere in the deploy script

## Answer

**Built:** `workflow_profile()` (`infra/scripts/deploy-aws-application.sh`)
is now a one-line pass-through: `command_task_profile "${1//_/-}"`. The
`${var//_/-}` substitution matches this file's own existing convention for
the identical underscore-to-hyphen translation
(`upsert_state_machine`'s `name="${NAME_PREFIX}-${workflow//_/-}"`), rather
than introducing a new idiom. The former case statement — including the two
genuinely dead `daily_incremental`/`bootstrap` arms plus the seven real
`bootstrap_full`/`targeted_resync`/`full_reconcile`/
`load_daily_form_index_for_date`/`catch_up_daily_form_index`/`gold_refresh`/
`seed_universe` arms — is retired. The one real production caller (the
`workflow_profile "$workflow"` loop building the 7 standalone state
machines) is untouched; its signature and behavior are unchanged.

Comments around both functions were updated to describe the post-migration
state rather than leave a stale "nothing has switched over yet" narrative
next to code that now fully delegates — including correcting
`command_task_profile()`'s own inline comments for `daily-incremental`/
`bootstrap`/`bootstrap-next`, which still described
`write_warehouse_mdm_gold_definition`/`write_load_history_definition` as
hardcoding ARNs directly (true before tickets 02/03, stale after).

**Proof this is a genuine pass-through, not coincidental agreement:** new
test file `tests/architecture/test_workflow_profile_pass_through_routing.py`
(14 tests), mirroring tickets 02/03's stub-override-after-sourcing
technique: sources the real `command_task_profile()`, then `workflow_profile()`,
then redefines `command_task_profile()` with a stub and confirms
`workflow_profile()`'s answer flips to match — plus a strict-stub test
confirming the exact hyphenated command name is passed, a fail-closed test
for an unknown workflow, and a direct assertion that `workflow_profile()`'s
extracted source contains no `case` keyword at all (a structural regression
guard, not just a behavioral one).

**Byte-identical resolution, verified analytically for all 7 real
workflows:** generated `workflow_profile()` + `task_definition_for_profile()`'s
resolved ARN for every workflow the real production loop iterates
(`bootstrap_full`, `targeted_resync`, `full_reconcile`,
`load_daily_form_index_for_date`, `catch_up_daily_form_index`,
`gold_refresh`, `seed_universe`) from the commit immediately before this
change and from the current working tree — identical for all 7.

**Existing tests updated to source the new internal dependency:**
`test_task_profile_source_of_truth.py` and
`test_source_export_commands_task_sizing.py` both extract `workflow_profile()`
in isolation; both now also extract+source `command_task_profile()` first,
matching the pattern tickets 02/03 already established for the other two
call sites. `test_task_profile_source_of_truth.py`'s module docstring got an
appended UPDATE note: with tickets 02-04 all landed, all three of its
"legacy mechanism" paths now resolve through `command_task_profile()`
themselves, so it's no longer an independent cross-check — it's a
regression-lock. Left as-is (not restructured) since ticket 05 only scopes
the sibling file's collapse; flagged for whoever revisits ticket 05's scope
next, not fixed here.

**Full suite:** clean — 2262 passed, 4 skipped, plus the 2 pre-existing,
already-documented, unrelated `test_bootstrap_dbt_snowflake_secret.py`
failures. mypy clean on the new/touched test files (the one pre-existing,
unrelated `test_source_export_commands_task_sizing.py` type error —
confirmed via `git stash` to predate this change, just shifted line number —
is untouched).
