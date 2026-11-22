#!/usr/bin/env bash
# Stamp, guard, commit and push in one step, so a failed guard cannot be walked past.
#
# Never type a time in a ticket: write {{now}} and this script puts the clock's ET time there
# (scripts/dev/future_stamps.py --stamp). It then stages everything in the worktree (new files too: one worktree per
# ticket), runs the
# overlap guard, and only when the guard exits 0 does it commit the message file and push. Any failure stops it
# (a guard run chained with `;` let a guessed stamp be committed and pushed on 2026-11-10).
#
# Usage: bash scripts/dev/commit_push.sh <commit-message-file>
set -euo pipefail

message="${1:?usage: commit_push.sh <commit-message-file>}"
here="$(dirname "$0")"

# Do this before stamping or staging: reusing a branch after its PR is closed
# can push commits that have no open review.
branch="$(git branch --show-current)"
if [[ -z "$branch" ]]; then
  echo "commit_push: STOP. Cannot determine the current branch; no files were stamped or staged." >&2
  exit 1
fi

if ! closed_prs="$(gh pr list --state all --head "$branch" --limit 1000 --json number,state \
  --jq '.[] | select(.state == "CLOSED" or .state == "MERGED") | "#\(.number) (\(.state))"')"; then
  echo "commit_push: STOP. Could not check GitHub PR state for '$branch'; no files were stamped or staged." >&2
  exit 1
fi

if [[ -n "$closed_prs" ]]; then
  printf "commit_push: STOP. Branch '%s' already has closed PR(s):\n%s\n" "$branch" "$closed_prs" >&2
  echo "Create a fresh branch for follow-up work; no files were stamped or staged." >&2
  exit 1
fi

uv run --no-project python "$here/future_stamps.py" --stamp
git add -A
bash "$here/overlap_guard.sh"
git commit -q -F "$message"
git push -q -u origin HEAD
