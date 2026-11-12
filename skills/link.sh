#!/usr/bin/env bash
# Link this repository's skills into the shared skills folder and into Claude's, so
# Claude, Codex and Grok all load the same copy from this checkout.
#
# Usage: bash skills/link.sh [--home directory] [skill ...]
# With no skill named, every folder here that holds a SKILL.md is linked. It never
# replaces a path it did not make: remove that path first, then run it again.
set -euo pipefail

task_home="${HOME}"
if [[ "${1:-}" == "--home" ]]; then
  [[ -n "${2:-}" ]] || { echo "usage: $0 [--home directory] [skill ...]" >&2; exit 2; }
  task_home="$2"
  shift 2
fi

skills_path="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ $# -eq 0 ]]; then
  for skill_file in "$skills_path"/*/SKILL.md; do
    set -- "$@" "$(basename "$(dirname "$skill_file")")"
  done
fi

# Validate every destination before changing any; preserve unrelated paths.
for skill in "$@"; do
  skill_path="$skills_path/$skill"
  [[ -f "$skill_path/SKILL.md" ]] || { echo "no such skill: $skill" >&2; exit 2; }
  shared_link="$task_home/.agents/skills/$skill"
  claude_link="$task_home/.claude/skills/$skill"
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
done

mkdir -p "$task_home/.agents/skills" "$task_home/.claude/skills"
for skill in "$@"; do
  shared_link="$task_home/.agents/skills/$skill"
  claude_link="$task_home/.claude/skills/$skill"
  [[ -L "$shared_link" ]] || ln -s "$skills_path/$skill" "$shared_link"
  [[ -L "$claude_link" ]] || ln -s "$shared_link" "$claude_link"
  echo "linked $claude_link -> $shared_link -> $skills_path/$skill"
done
