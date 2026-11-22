# The commit and watch scripts no longer carry a conflicting PR

Status: resolved
Type: task

Operator, 2026-11-22: "2034 ci not running", then "there is a problem with commit and create pr script fix it".
Root cause: `commit_push.sh` never checked the branch against `origin/main`, so a PR was created conflicting, GitHub starts no CI on a
conflicting PR, and `merge_on_green.sh` waited for runs that never came until its deadline (#2029 and #2034 both).

## Checklist

- [x] Tests first, both failed: the watcher timed out waiting on a conflicting PR (no exit), and `commit_push.sh` committed and pushed a branch behind main (exit 0) 2026-11-22 16:31 ET
- [x] `merge_on_green.sh` exits 1 at once on a conflicting PR (`mergeStateStatus` DIRTY) with the rebase instruction 2026-11-22 16:31 ET
- [x] `commit_push.sh` refuses a branch behind `origin/main` before stamping or staging, and pushes with `--force-with-lease` so a rebased branch can be updated 2026-11-22 16:31 ET
- [x] Tests: `tests/unit/test_pr_scripts_refuse_a_conflicting_branch.py` and `test_merge_on_green_keeps_worktree.py` pass (4) 2026-11-22 16:31 ET
- [x] Learning → skill: none; the rule belongs to the two scripts' own header comments 2026-11-22 16:31 ET

## Answer

Both scripts now stop on a conflicting or stale branch instead of silently carrying it. There is still no script that creates the PR: `gh pr create` stays by hand.
