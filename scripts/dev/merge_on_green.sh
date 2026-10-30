#!/usr/bin/env bash
# Merge a PR only when every CI run of its current head commit has passed.
#
# Reads the head commit each round, and counts only the workflow runs of that
# commit: right after a push, `gh pr checks` still lists the previous commit's
# green checks, and a watcher reading them merged code CI had not run (#1185,
# 2026-10-26; #1245, 2026-10-30). The merge names the head it saw
# (--match-head-commit), so a push in between makes GitHub refuse it.
# A base that moved is updated, and the new head waits for its own CI.
#
# Exit 0: merged, or the PR was closed or merged by someone else.
# Exit 1: a run failed or was cancelled. Exit 2: the deadline passed.
# Usage: bash scripts/dev/merge_on_green.sh <pr> [minutes, default 60]
set -euo pipefail

pr="$1"
deadline=$(( $(date +%s) + ${2:-60} * 60 ))

while (( $(date +%s) < deadline )); do
  sleep 60
  state=$(gh pr view "$pr" --json state -q .state)
  if [[ "$state" != OPEN ]]; then echo "PR $pr is $state"; exit 0; fi
  head=$(gh pr view "$pr" --json headRefOid -q .headRefOid)
  runs=$(gh run list --commit "$head" --json status,conclusion,name \
           -q '.[] | .name + "\t" + .status + "\t" + (.conclusion // "")')
  [[ -z "$runs" ]] && continue                      # CI not started on this head yet
  if awk -F'\t' '$2 != "completed" {found = 1} END {exit !found}' <<<"$runs"; then continue; fi
  failed=$(awk -F'\t' '$3 !~ /^(success|skipped|neutral)$/' <<<"$runs")
  if [[ -n "$failed" ]]; then echo "CI failed on ${head:0:8}:"; echo "$failed"; exit 1; fi
  if [[ $(gh pr view "$pr" --json mergeStateStatus -q .mergeStateStatus) == BEHIND ]]; then
    gh pr update-branch "$pr" >/dev/null && echo "base moved: updated, waiting for CI again"
    continue
  fi
  gh pr merge "$pr" --squash --match-head-commit "$head"
  echo "merged ${head:0:8}"
  exit 0
done
echo "deadline passed"
exit 2
