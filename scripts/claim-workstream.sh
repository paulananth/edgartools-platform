#!/usr/bin/env bash
# claim-workstream.sh — register or release a worktree in .planning/REGISTRY.md
#
# Usage:
#   claim-workstream.sh claim <workstream> <runtime> [options]
#   claim-workstream.sh release <workstream>
#   claim-workstream.sh status
#
# Options for claim:
#   --phase <phase>        Current phase (e.g. "Phase 5")
#   --plan  <plan>         Current plan (e.g. "05-01" or "TBD")
#   --blocking <list>      Comma-separated list of workstreams this blocks
#
# Examples:
#   claim-workstream.sh claim neo4j-pipe Claude --phase "Phase 5" --plan "TBD"
#   claim-workstream.sh claim neo4j-snowflake Codex --phase "Phase 3" --plan "TBD" --blocking "neo4j-pipe"
#   claim-workstream.sh release neo4j-pipe
#   claim-workstream.sh status

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REGISTRY="$REPO_ROOT/.planning/REGISTRY.md"

WORKTREE_BASE="/Users/aneenaananth/gsd-workspaces"
BRANCH_PREFIX="workspace"

usage() {
  grep '^#' "$0" | head -20 | sed 's/^# \{0,1\}//'
  exit 1
}

cmd="${1:-}"
case "$cmd" in
  claim)
    workstream="${2:-}"
    runtime="${3:-}"
    [[ -z "$workstream" || -z "$runtime" ]] && usage

    shift 3
    phase="TBD"
    plan="TBD"
    blocking="—"

    while [[ $# -gt 0 ]]; do
      case "$1" in
        --phase)    phase="$2";    shift 2 ;;
        --plan)     plan="$2";     shift 2 ;;
        --blocking) blocking="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
      esac
    done

    branch="$BRANCH_PREFIX/$workstream"
    worktree_path="$WORKTREE_BASE/$workstream/edgartools-platform"
    claimed_at="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    last_session="$(date -u '+%Y-%m-%d')"

    # Build the entry block
    entry="### $workstream

| Field | Value |
|-------|-------|
| **Runtime** | $runtime |
| **Status** | active |
| **Branch** | \`$branch\` |
| **Worktree path** | \`$worktree_path\` |
| **Claimed at** | $claimed_at |
| **Last session** | $last_session |
| **Current phase** | $phase |
| **Current plan** | $plan |
| **Blocking** | $blocking |"

    # Check if entry already exists — replace or append
    if grep -q "^### $workstream$" "$REGISTRY" 2>/dev/null; then
      # Replace existing block (between ### workstream and next ### or EOF)
      python3 - "$REGISTRY" "$workstream" "$entry" <<'PYEOF'
import sys, re
path, name, new_entry = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    content = f.read()
# Replace block from ### name to next ### or end of Active Workstreams section
pattern = rf'### {re.escape(name)}\n.*?(?=\n### |\n---|\Z)'
new = re.sub(pattern, new_entry.strip(), content, flags=re.DOTALL)
with open(path, 'w') as f:
    f.write(new)
PYEOF
      echo "✅ Updated $workstream in REGISTRY.md ($runtime, $phase)"
    else
      # Append under ## Active Workstreams
      python3 - "$REGISTRY" "$entry" <<'PYEOF'
import sys
path, entry = sys.argv[1], sys.argv[2]
with open(path) as f:
    content = f.read()
marker = "## Active Workstreams"
idx = content.find(marker)
if idx == -1:
    print(f"ERROR: could not find '{marker}' in {path}", file=sys.stderr)
    sys.exit(1)
# Find end of the marker line
eol = content.index('\n', idx) + 1
insert_at = eol
# Skip any blank line after the header
while insert_at < len(content) and content[insert_at] == '\n':
    insert_at += 1
new = content[:insert_at] + entry.strip() + '\n\n' + content[insert_at:]
with open(path, 'w') as f:
    f.write(new)
PYEOF
      echo "✅ Claimed $workstream in REGISTRY.md ($runtime, $phase)"
    fi
    ;;

  release)
    workstream="${2:-}"
    [[ -z "$workstream" ]] && usage

    if ! grep -q "^### $workstream$" "$REGISTRY" 2>/dev/null; then
      echo "⚠️  $workstream not found in REGISTRY.md"
      exit 0
    fi

    # Mark status as released and update last_session
    last_session="$(date -u '+%Y-%m-%d')"
    python3 - "$REGISTRY" "$workstream" "$last_session" <<'PYEOF'
import sys, re
path, name, last_session = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    content = f.read()
# Update Status field within the block
pattern = rf'(### {re.escape(name)}\n.*?\*\*Status\*\* \| )active(.*?(?=\n### |\n---|\Z))'
content = re.sub(pattern, r'\1released\2', content, flags=re.DOTALL)
# Update Last session field
pattern2 = rf'(### {re.escape(name)}\n.*?\*\*Last session\*\* \| )\S+(.*?(?=\n### |\n---|\Z))'
content = re.sub(pattern2, rf'\g<1>{last_session}\2', content, flags=re.DOTALL)
with open(path, 'w') as f:
    f.write(content)
PYEOF
    echo "✅ Released $workstream in REGISTRY.md"
    ;;

  status)
    if [[ ! -f "$REGISTRY" ]]; then
      echo "REGISTRY.md not found at $REGISTRY"
      exit 1
    fi
    echo ""
    grep -E "^### |Runtime|Status|Phase|Blocking" "$REGISTRY" | \
      sed 's/^| \*\*\(.*\)\*\* | \(.*\) |/  \1: \2/' | \
      sed 's/^### /\n🔲 /'
    echo ""
    ;;

  *)
    usage
    ;;
esac
