#!/usr/bin/env bash
# Create the local bookkeeping and Change Ledger databases on the Clean MDM
# PostgreSQL 16 instance and install their schemas.
#
# MDM stays in `mdm`. Bookkeeping and the Change Ledger each get their own
# database on the same loopback instance. Production still co-hosts the
# Change Ledger on the MDM instance unless CHANGE_LEDGER_DATABASE_URL is set.
#
# Usage:
#   bash infra/scripts/provision-local-postgres-stores.sh
#   bash infra/scripts/provision-local-postgres-stores.sh --drop-ledger-from-mdm

set -euo pipefail

DROP_LEDGER_FROM_MDM=false
CONTAINER="edgartools-clean-mdm-pg16"
USER_NAME="postgres"
PASSWORD="test"
MDM_DATABASE="mdm"
BOOKKEEPING_DATABASE="bookkeeping"
CHANGE_LEDGER_DATABASE="change_ledger"
BIND="127.0.0.1:5432"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --drop-ledger-from-mdm) DROP_LEDGER_FROM_MDM=true; shift ;;
        --help|-h)
            sed -n '2,16p' "$0"
            exit 0
            ;;
        *) echo "Unknown flag: $1" >&2; exit 2 ;;
    esac
done

log() { echo "==> $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -S "$HOME/.colima/default/docker.sock" ]]; then
    export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
fi

bash "$ROOT/infra/scripts/start-local-postgres.sh" >/dev/null

psql_admin() {
    docker exec -e PGPASSWORD="$PASSWORD" "$CONTAINER" \
        psql -U "$USER_NAME" -d postgres -v ON_ERROR_STOP=1 "$@"
}

psql_db() {
    local db="$1"
    shift
    docker exec -e PGPASSWORD="$PASSWORD" "$CONTAINER" \
        psql -U "$USER_NAME" -d "$db" -v ON_ERROR_STOP=1 "$@"
}

ensure_database() {
    local name="$1"
    local exists
    exists="$(
        psql_admin -Atc "SELECT 1 FROM pg_database WHERE datname = '${name}'"
    )"
    if [[ -z "$exists" ]]; then
        log "Creating database ${name}"
        psql_admin -c "CREATE DATABASE ${name}"
    else
        log "Database ${name} already exists"
    fi
    psql_admin -c "GRANT CONNECT ON DATABASE ${name} TO application"
    psql_db "$name" -c "GRANT USAGE ON SCHEMA public TO application"
}

ensure_database "$BOOKKEEPING_DATABASE"
ensure_database "$CHANGE_LEDGER_DATABASE"

BOOKKEEPING_URL="postgresql://${USER_NAME}:${PASSWORD}@${BIND}/${BOOKKEEPING_DATABASE}"
CHANGE_LEDGER_URL="postgresql://${USER_NAME}:${PASSWORD}@${BIND}/${CHANGE_LEDGER_DATABASE}"
MDM_URL="postgresql://${USER_NAME}:${PASSWORD}@${BIND}/${MDM_DATABASE}"

log "Installing bookkeeping schema"
(cd "$ROOT" && uv run python infra/scripts/provision_bookkeeping_schema.py \
    --database-url "$BOOKKEEPING_URL" --grant-role application)

log "Installing Change Ledger schema"
(cd "$ROOT" && uv run python infra/scripts/provision_change_ledger_schema.py \
    --database-url "$CHANGE_LEDGER_URL")

if [[ "$DROP_LEDGER_FROM_MDM" == "true" ]]; then
    log "Dropping Change Ledger tables from ${MDM_DATABASE} (they now live in ${CHANGE_LEDGER_DATABASE})"
    psql_db "$MDM_DATABASE" -c "
DROP TABLE IF EXISTS
    source_evidence_conflict,
    source_evidence_import,
    source_expected_producer,
    source_fetch_transition,
    source_fetch_work,
    source_fetch_decision,
    source_processing_decision,
    source_observation_cursor,
    source_registry_coverage,
    source_registry_version,
    source_revision
CASCADE;
"
fi

log "mdm:           $MDM_URL"
log "bookkeeping:   $BOOKKEEPING_URL"
log "change_ledger: $CHANGE_LEDGER_URL"
log "export MDM_DATABASE_URL=$MDM_URL"
log "export BOOKKEEPING_DATABASE_URL=$BOOKKEEPING_URL"
log "export CHANGE_LEDGER_DATABASE_URL=$CHANGE_LEDGER_URL"
