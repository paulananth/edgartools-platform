#!/usr/bin/env bash
# Stop before a commit or push that touches a file another runtime is changing.
#
# Compares the files this branch changes (committed since origin/main, staged,
# unstaged and untracked) with the files changed by:
#   - every open PR whose branch belongs to another runtime;
#   - every worktree of another runtime: its unmerged branch changes and its
#     uncommitted files.
# A branch is another runtime's when its prefix (before the first "/") differs
# from this branch's prefix. A file counts as changed on a branch only if it
# differs from origin/main now, so squash-merged branches do not count.
#
# Exit 0: no overlap. Exit 1: each overlapping file and who holds it.
# Usage: bash scripts/dev/overlap_guard.sh  [--base origin/main]
set -euo pipefail

base="origin/main"
if [[ "${1:-}" == "--base" ]]; then base="$2"; fi

branch="$(git branch --show-current)"
if [[ -z "$branch" || "$branch" != */* ]]; then
  echo "overlap_guard: the current branch '$branch' has no runtime prefix (e.g. claude/<topic>)" >&2
  exit 1
fi
mine="${branch%%/*}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# Files a branch changes and that still differ from the base.
branch_files() {
  comm -12 <(git diff --name-only "$base...$1" | sort -u) \
           <(git diff --name-only "$base" "$1" | sort -u)
}

# Uncommitted files of a worktree (staged, unstaged, untracked).
dirty_files() {
  git -C "$1" status --porcelain --untracked-files=all | cut -c4- | sed 's/.* -> //' | sort -u
}

{ branch_files HEAD; dirty_files .; } | sort -u > "$tmp/mine"
if [[ ! -s "$tmp/mine" ]]; then
  echo "overlap_guard: this branch changes no files"
  exit 0
fi

: > "$tmp/theirs"   # lines: <file>\t<holder>

# Open PRs of other runtimes.
if command -v gh >/dev/null 2>&1; then
  gh pr list --state open --limit 100 --json number,headRefName,files \
    --jq '.[] | . as $pr | $pr.files[] | "\(.path)\tPR #\($pr.number) (\($pr.headRefName))"' \
    2>/dev/null | while IFS=$'\t' read -r path holder; do
      ref="${holder#*(}"; ref="${ref%)}"
      [[ "${ref%%/*}" == "$mine" ]] || printf '%s\t%s\n' "$path" "$holder"
    done >> "$tmp/theirs"
else
  echo "overlap_guard: gh is not installed; open PRs were not checked" >&2
  exit 1
fi

# Worktrees of other runtimes.
git worktree list --porcelain | awk '/^worktree /{w=substr($0,10)} /^branch /{print w "\t" substr($0,19)}' \
  | while IFS=$'\t' read -r path ref; do
      [[ "$ref" == */* && "${ref%%/*}" != "$mine" ]] || continue
      { branch_files "$ref"; dirty_files "$path"; } | sort -u \
        | sed "s|\$|\tworktree $path ($ref)|"
    done >> "$tmp/theirs"

overlap="$(awk -F'\t' 'NR==FNR{m[$0]=1; next} ($1 in m){print "  " $1 "  <-  " $2}' "$tmp/mine" "$tmp/theirs" | sort -u)"
if [[ -n "$overlap" ]]; then
  echo "overlap_guard: STOP. These files are also being changed by another runtime:"
  echo "$overlap"
  echo "Ask the operator before committing or pushing."
  exit 1
fi
echo "overlap_guard: no overlap ($(wc -l < "$tmp/mine" | tr -d ' ') files checked against other runtimes)"
