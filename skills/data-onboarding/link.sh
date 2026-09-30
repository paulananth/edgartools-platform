#!/usr/bin/env bash
# Link this repo's `data-onboarding` skill into the shared skills folder and into
# Claude's, so Claude, Codex and Grok all load the same copy. Same shape as
# skills/bookkeeping/link.sh.
set -euo pipefail

task_home="${HOME}"
if [[ $# -eq 2 && "$1" == "--home" && -n "$2" ]]; then
  task_home="$2"
elif [[ $# -ne 0 ]]; then
  echo "usage: $0 [--home directory]" >&2
  exit 2
fi

skill_path="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
shared_link="${task_home}/.agents/skills/data-onboarding"
claude_link="${task_home}/.claude/skills/data-onboarding"

# Validate both destinations before changing either; preserve unrelated paths.
for link_path in "$shared_link" "$claude_link"; do
  if [[ -e "$link_path" || -L "$link_path" ]]; then
    expected_target="$skill_path"
    [[ "$link_path" != "$claude_link" ]] || expected_target="$shared_link"
    if [[ ! -L "$link_path" || "$(readlink "$link_path")" != "$expected_target" ]]; then
      echo "refusing to replace existing path: $link_path" >&2
      exit 1
    fi
  fi
done

mkdir -p "$(dirname "$shared_link")" "$(dirname "$claude_link")"
[[ -L "$shared_link" ]] || ln -s "$skill_path" "$shared_link"
[[ -L "$claude_link" ]] || ln -s "$shared_link" "$claude_link"
echo "linked $shared_link -> $skill_path"
echo "linked $claude_link -> $shared_link"
