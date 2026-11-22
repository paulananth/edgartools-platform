# Stop commits to branches with closed PRs

Status: resolved

## Root cause

- **Problem:** the commit helper could add a new commit to a branch after its PR was merged or closed; commit `4fccb5ce` followed merged PR #1927 and is not in `origin/main`.
- **Root cause:** it did not inspect the current branch's PR lifecycle before stamping files and staging the worktree.
- **Fix:** query all PRs for the branch first; stop on a closed or merged PR and stop if GitHub cannot answer.
- **Lesson:** create a fresh branch for follow-up work; the commit helper now enforces that lifecycle boundary before it changes files.

## Parts

- [x] Record the root cause and scope from the closed-PR branch evidence. 2026-11-22 11:02 ET
- [x] Add a pre-staging lifecycle check that blocks closed or merged PR branches and fails closed when GitHub cannot be queried. 2026-11-22 11:02 ET
- [x] Review the changed script under Standards, Spec and GoF; no local tests were run under the current instruction. 2026-11-22 11:02 ET
- [x] Learning → skill: none; enforce branch reuse prevention directly in `commit_push.sh`. 2026-11-22 11:03 ET

## Review

- **Standards:** no findings; the guard runs before stamping/staging and fails closed on GitHub query errors. Timestamp helper uses `uv`.
- **Spec:** no findings; closed/merged branches stop, open/no-PR branches continue.
- **GoF:** no pattern refactor; retain the direct guard in the linear shell workflow.
