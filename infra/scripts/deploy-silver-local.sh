#!/usr/bin/env bash
# Deploy silver to a local test environment: migrate the silver database and
# register every committed silver table spec (rules/sources/*/silver-*.yaml).
# Safe to repeat: an unchanged spec changes nothing; a changed one is refused.
#
#   bash infra/scripts/deploy-silver-local.sh <environment-name>
#
# The environment must hold silver (create it with
# `local-test-stores.py up <name>`). Prints table names only,
# never a connection value.
set -euo pipefail

name="${1:?usage: deploy-silver-local.sh <environment-name>}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
env_file="${EDGARTOOLS_LOCAL_TESTS:-$HOME/.local/share/edgartools/local-tests}/environments/$name/connection.env"
[ -f "$env_file" ] || { echo "No environment named $name" >&2; exit 2; }

set -a; . "$env_file"; set +a
[ -n "${SILVER_MIGRATION_DATABASE_URL:-}" ] || {
  echo "Environment $name holds no silver; run: local-test-stores.py up $name" >&2; exit 2; }

cd "$root"
run() { uv run --no-sync edgar-warehouse "$@"; }

run silver migrate --runtime-role silver_runtime >/dev/null
for spec in rules/sources/*/silver-*.yaml; do
  run silver register --runtime-role silver_runtime "$spec" | python3 -c \
    'import json,sys; r=json.load(sys.stdin); print(("created  " if r["created"] else "unchanged ")+r["table"])'
done
