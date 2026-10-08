#!/usr/bin/env bash
# Profiling ticket 08: the cold agent's sandbox.
#
# A copy of the repository at one commit with every answer taken out: no
# rules (sources, merge rules, reference data, pipelines, context), no
# tickets or maps (.scratch, .planning), no tests (their fixtures and digests
# name today's rules), no generated mapping documents, no qualification
# scripts or internal docs, no CLAUDE.md or AGENTS.md. The skills, the
# platform code and the specs stay; still-named.txt lists every file that
# still names SEC submissions or GLEIF, for DIFF.md to explain. The cohort's sliced inputs and the
# rulings file are copied in. env.sh points EDGAR_RULES_ROOT at an empty
# rules folder the agent fills, and sets unreachable proxies with NO_PROXY
# cleared (this stops clients that honour proxy variables, not raw sockets).
# The proof's own run, not this script, makes the disposable PostgreSQL where
# approvals are recorded, marked "replayed".
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
BOX=$(cd "$BOX" && pwd)
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
unset NO_PROXY no_proxy
EOF
# Nothing that holds an answer is left in.
for gone in rules .scratch .planning tests; do
  [ ! -e "$BOX/repo/$gone" ] || { echo "$gone left in the sandbox" >&2; exit 1; }
done
# Files that still name a feed the agent regenerates (SEC submissions, GLEIF;
# 13F is silver, ticket 06): the platform code and the skills' Examples
# sections. Listed for DIFF.md, which explains each. grep exits 1 for none.
set +e
grep -rIl -e 'sec\.submissions\.' -e 'gleif\.' "$BOX/repo" > "$BOX/still-named.raw"
status=$?
set -e
[ "$status" -le 1 ] || { echo "grep failed ($status)" >&2; exit 1; }
sed "s#^$BOX/repo/##" "$BOX/still-named.raw" | sort > "$BOX/still-named.txt"
rm "$BOX/still-named.raw"
echo "still naming a feed: $(wc -l < "$BOX/still-named.txt") files (still-named.txt)"
echo "sandbox $BOX at $COMMIT: $(du -sh "$BOX" | cut -f1)"
