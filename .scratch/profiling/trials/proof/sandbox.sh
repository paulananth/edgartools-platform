#!/usr/bin/env bash
# Profiling ticket 08: the cold agent's sandbox.
#
# A copy of the repository at one commit with every answer taken out: no
# rules (sources, merge rules, reference data, pipelines, context), no
# tickets or maps (.scratch, .planning), no tests (their fixtures and digests
# name today's rules), no generated mapping documents. The skills, the
# platform code and the specs stay; still-named.txt lists every file that
# still names a feed, for DIFF.md to explain. The cohort's sliced inputs and the
# rulings file are copied in. EDGAR_RULES_ROOT points at an empty rules
# folder the agent fills. Approvals are recorded only on the sandbox's own
# disposable PostgreSQL, marked "replayed".
#
#   bash .scratch/profiling/trials/proof/sandbox.sh <commit> <sandbox folder>
set -euo pipefail
COMMIT=${1:?commit}
BOX=${2:?sandbox folder}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
INPUTS=$HOME/.local/share/edgartools/clean-mdm/proving/p08/inputs
[ -e "$BOX" ] && { echo "$BOX exists: a sandbox is made once" >&2; exit 1; }
[ -f "$INPUTS/SLICE.json" ] || { echo "no slice: run slice.py first" >&2; exit 1; }
mkdir -p "$BOX/repo" "$BOX/rules"
git -C "$REPO" archive "$COMMIT" | tar -x -C "$BOX/repo"
rm -rf "$BOX/repo/rules" "$BOX/repo/.scratch" "$BOX/repo/.planning" "$BOX/repo/tests" \
  "$BOX/repo/docs/research" "$BOX/repo/docs-internal" "$BOX/repo/scripts/qualification" \
  "$BOX/repo/TODOS.md" "$BOX/repo/CLAUDE.md" "$BOX/repo/AGENTS.md"
find "$BOX/repo" -name 'MAPPING.xlsx' -delete
cp -R "$INPUTS" "$BOX/inputs"
cp "$HERE/rulings.jsonl" "$BOX/rulings.jsonl"
cat > "$BOX/env.sh" <<EOF
export EDGAR_RULES_ROOT="$BOX/rules"
export HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9
export https_proxy=http://127.0.0.1:9 http_proxy=http://127.0.0.1:9
export AWS_ACCESS_KEY_ID=blocked AWS_SECRET_ACCESS_KEY=blocked
EOF
# Nothing that holds an answer is left in.
for gone in rules .scratch .planning tests; do
  [ ! -e "$BOX/repo/$gone" ] || { echo "$gone left in the sandbox" >&2; exit 1; }
done
# Files that still name a feed the agent regenerates: the platform code and the
# skills' Examples sections. Listed for DIFF.md, which explains each.
grep -rIl -e 'sec\.submissions\.' -e 'gleif\.' "$BOX/repo" | sed "s#^$BOX/repo/##" | sort > "$BOX/still-named.txt" || true
echo "still naming a feed: $(wc -l < "$BOX/still-named.txt") files (still-named.txt)"
echo "sandbox $BOX at $COMMIT: $(du -sh "$BOX" | cut -f1)"
