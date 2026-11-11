# Confirmed-government branch closeout research

## Finding

The local branch `codex/confirmed-government-20261105` is represented by merged PR [#1448](https://github.com/paulananth/edgartools-platform/pull/1448). Its head `4fb85a00` is an ancestor of PR head `171998c0`; squash merge `b56e6fb6` is in `origin/main` (`5dd4d691`). The branch's aggregate patch and the PR's aggregate patch have the same stable patch ID, `a7d13290e184653086f2664447b0af6639a486dd`.

## Evidence and limits

- `git merge-base --is-ancestor 4fb85a00 171998c0` and `git merge-base --is-ancestor b56e6fb6 origin/main` succeed. A squash merge does not make the PR head an ancestor of main.
- `git diff 90a3bc85 4fb85a00 | git patch-id --stable` matches `git diff e97f6c4e 171998c0 | git patch-id --stable`; the first range uses the branch's merge base with main, the second the PR base and head.
- PR #1448 records native readback and repeat-repair evidence. It distinguishes source-reported fund associations from mastered relationships, records that the N-PORT Security run and physical holdings table were not present, and identifies issue #1447 for the runtime guard.
- The old branch is checked out in a clean linked worktree. Preserve the worktree while removing the redundant branch ref after publication.

## Disposition

No source changes need to be transplanted. The branch's changes were included in PR #1448; retain its stated evidence limits.
