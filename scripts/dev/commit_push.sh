#!/usr/bin/env bash
# Stamp, guard, commit and push in one step, so a failed guard cannot be walked past.
#
# Never type a time in a ticket: write {{now}} and this script puts the clock's ET time there
# (scripts/dev/future_stamps.py --stamp). It then stages the branch's tracked changes and .scratch, runs the
# overlap guard, and only when the guard exits 0 does it commit the message file and push. Any failure stops it
# (a guard run chained with `;` let a guessed stamp be committed and pushed on 2026-11-10).
#
# Usage: bash scripts/dev/commit_push.sh <commit-message-file>
set -euo pipefail

message="${1:?usage: commit_push.sh <commit-message-file>}"
here="$(dirname "$0")"

python3 "$here/future_stamps.py" --stamp
git add -u
git add -A .scratch
bash "$here/overlap_guard.sh"
git commit -q -F "$message"
git push -q -u origin HEAD
