#!/usr/bin/env bash
# Link this repo's `rules` skill into the shared skills folder, and into
# Claude's, so Claude, Codex and Grok all load the same copy.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
shared="${HOME}/.agents/skills/rules"
claude="${HOME}/.claude/skills/rules"

mkdir -p "$(dirname "$shared")" "$(dirname "$claude")"
for link in "$shared" "$claude"; do
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    echo "refusing: $link exists and is not a link" >&2
    exit 1
  fi
done
ln -sfn "$here" "$shared"
ln -sfn "$shared" "$claude"
echo "linked $shared -> $here"
echo "linked $claude -> $shared"
