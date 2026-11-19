#!/usr/bin/env bash
# Deploy silver to a store: migrate the silver database and register every committed
# silver table spec (rules/sources/*/silver-*.yaml, rules/silver/silver-*.yaml) with the silver owner's connection.
# Safe to repeat: an unchanged spec changes nothing; a changed one is refused.
#
#   bash infra/scripts/deploy-silver.sh <environment-name>      a local test environment
#   bash infra/scripts/deploy-silver.sh <path to owner.env>  any store, hosted included
#
# A local environment must hold silver (create it with `local-test-stores.py up <name>`).
# Prints table names only, never a connection value.
set -euo pipefail

name="${1:?usage: deploy-silver.sh <environment-name | path to owner.env>}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ "$name" == */* ]]; then
  env_file="$name"
else
  env_file="${EDGARTOOLS_LOCAL_TESTS:-$HOME/.local/share/edgartools/local-tests}/environments/$name/owner.env"
fi
[ -f "$env_file" ] || { echo "No environment or connection file named $name" >&2; exit 2; }

set -a; . "$env_file"; set +a
[ -n "${DB_URL:-}" ] || {
  echo "$name holds no owner login (DB_URL)" >&2; exit 2; }

cd "$root"
run() { uv run --no-sync edgar-warehouse "$@"; }

run silver init --runtime-role silver_runtime >/dev/null
for spec in rules/sources/*/silver-*.yaml rules/silver/silver-*.yaml; do
  run silver register --runtime-role silver_runtime "$spec" | python3 -c \
    'import json,sys; r=json.load(sys.stdin); print(("created  " if r["created"] else "unchanged ")+r["table"])'
done
