# 156: A fix names its failing test, and a merge removes its worktree

Priority: 156. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 17:55 ET, from the second retrospective of the ticket 150 session
(operator, 2026-11-01: "do 1, 2 and 5 first").

Type: task. Status: resolved on merge of the PR below (Claude, branch `claude/t156-retro-guards`). Blocked by: none.

## Question

Two repeats cost time: a regression test that passed on the unfixed code (ticket 152), and eight merged tickets' worktrees and
branches left for hand cleanup. Can the reviewer catch the first and the merge watcher do the second?

## Parts

- [x] CLAUDE.md, "Tests and CI": a fix PR names the test that failed before the fix and the assertion that failed; the Standards reviewer checks it (2026-11-01 17:56 ET)
- [x] `merge_on_green.sh` removes the merged PR's worktree and branch, keeps a worktree with unsaved files or on another branch: `tests/unit/test_merge_on_green_cleanup.py`, 3 tests, the removal test red before (worktree still there) and green after (2026-11-01 17:56 ET)
- [x] CLAUDE.md, watcher bullet: start the watcher itself as the background command, no `&`, no redirect (operator, 2026-11-01: "yes, restart the watcher and make that edit"; 2026-11-01 17:58 ET)
- [x] PR, CI green, merged: #1272 (the PR is the record; ticked 2026-11-04 04:42 ET)
- [x] Review fixes: the cleanup cannot fail the script after a merge (a failed `gh`, `cd` or branch delete is reported, exit stays 0), and the test names its assertion `assert not work.exists()` (2026-11-01 17:56 ET)
- [x] Learning → skill: CLAUDE.md, "Tests and CI" (the first part); the second part is script behaviour, no skill line
