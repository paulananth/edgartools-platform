#!/usr/bin/env bash
# Provision fresh Bookkeeping, Rules and Change Journal on local PostgreSQL 16.
# Existing legacy databases are retained unchanged; no history is imported.
# Set BOOKKEEPING_CLEAN_RUNTIME_PASSWORD, RULES_AGENT_PASSWORD and
# CHANGE_JOURNAL_RUNTIME_PASSWORD before running. No Rules approval is created.
set -euo pipefail
if [[ $# -gt 0 ]]; then
    echo "Fresh provisioning takes no flags; legacy physical retirement is separate." >&2
    exit 2
fi
: "${BOOKKEEPING_CLEAN_RUNTIME_PASSWORD:?Set the fresh runtime password}"
: "${RULES_AGENT_PASSWORD:?Set the Rules agent password}"
: "${CHANGE_JOURNAL_RUNTIME_PASSWORD:?Set the journal runtime password}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
bash "$ROOT/infra/scripts/start-local-postgres.sh" >/dev/null
export BOOKKEEPING_CLEAN_ADMIN_DATABASE_URL="${BOOKKEEPING_CLEAN_ADMIN_DATABASE_URL:-postgresql://postgres:test@127.0.0.1:5432/postgres}"
cd "$ROOT"
uv run --extra mdm infra/scripts/provision-clean-bookkeeping.py --rules --journal
