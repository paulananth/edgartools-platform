#!/usr/bin/env bash
# Start the Clean MDM local PostgreSQL 16 instance on loopback.
#
# This is the disposable operator Postgres from docs/specs/clean-mdm/acceptance.md:
# PostgreSQL 16, Colima Docker on macOS, bound only to 127.0.0.1, unique
# container/volume for this workstream. It is not a substitute for the
# ephemeral postgres:16-alpine fixtures in tests/integration/.
#
# PlanetScale Postgres and Neki are hosted products and are not open source.
# The only PlanetScale Postgres-related public repo (Lead) is a full-text
# search extension, not a server. Local work uses the same official image
# the integration tests already pin: postgres:16-alpine.
#
# Usage:
#   bash infra/scripts/start-local-postgres.sh           # create or start
#   bash infra/scripts/start-local-postgres.sh --status  # print DSN and version
#   bash infra/scripts/start-local-postgres.sh --stop    # stop, keep data
#   bash infra/scripts/start-local-postgres.sh --reset   # destroy container+volume
#
# After start, three databases on the same instance:
#   export MDM_DATABASE_URL="postgresql://postgres:test@127.0.0.1:5432/mdm"
#   export BOOKKEEPING_DATABASE_URL="postgresql://postgres:test@127.0.0.1:5432/bookkeeping"
#   export CHANGE_LEDGER_DATABASE_URL="postgresql://postgres:test@127.0.0.1:5432/change_ledger"
#
# Creating the container only creates `mdm`. Provision the other two with:
#   bash infra/scripts/provision-local-postgres-stores.sh

set -euo pipefail

ACTION=start
CONTAINER="edgartools-clean-mdm-pg16"
VOLUME="edgartools-clean-mdm-pg16-data"
IMAGE="postgres:16-alpine"
USER_NAME="postgres"
PASSWORD="test"
DATABASE="mdm"
BOOKKEEPING_DATABASE="bookkeeping"
CHANGE_LEDGER_DATABASE="change_ledger"
BIND="127.0.0.1:5432"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --status) ACTION=status; shift ;;
        --stop)   ACTION=stop; shift ;;
        --reset)  ACTION=reset; shift ;;
        --help|-h)
            sed -n '2,24p' "$0"
            exit 0
            ;;
        *) echo "Unknown flag: $1" >&2; exit 2 ;;
    esac
done

log() { echo "==> $*"; }
fail() { echo "ERROR: $*" >&2; exit 1; }

ensure_docker() {
    if [[ -S "$HOME/.colima/default/docker.sock" ]]; then
        export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
    fi
    command -v docker >/dev/null 2>&1 || fail "docker CLI is not installed"
    if ! docker info >/dev/null 2>&1; then
        fail "Docker daemon is not reachable. On macOS start Colima, then: export DOCKER_HOST=unix://\$HOME/.colima/default/docker.sock"
    fi
}

container_state() {
    docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || true
}

wait_healthy() {
    local i status
    for i in $(seq 1 24); do
        status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER")"
        if [[ "$status" == "healthy" ]]; then
            return 0
        fi
        sleep 1
    done
    fail "PostgreSQL container '$CONTAINER' did not become healthy"
}

print_status() {
    local state version
    state="$(container_state)"
    [[ -n "$state" ]] || fail "container '$CONTAINER' does not exist"
    log "container: $CONTAINER ($state)"
    log "image:     $IMAGE"
    log "bind:      $BIND"
    log "mdm:            postgresql://${USER_NAME}:${PASSWORD}@${BIND}/${DATABASE}"
    log "bookkeeping:    postgresql://${USER_NAME}:${PASSWORD}@${BIND}/${BOOKKEEPING_DATABASE}"
    log "change_ledger:  postgresql://${USER_NAME}:${PASSWORD}@${BIND}/${CHANGE_LEDGER_DATABASE}"
    if [[ "$state" == "running" ]]; then
        version="$(
            docker exec -e PGPASSWORD="$PASSWORD" "$CONTAINER" \
                psql -U "$USER_NAME" -d "$DATABASE" -Atc "SHOW server_version;"
        )"
        log "version:   $version"
    fi
}

ensure_docker

case "$ACTION" in
    status)
        print_status
        ;;
    stop)
        state="$(container_state)"
        [[ -n "$state" ]] || fail "container '$CONTAINER' does not exist"
        if [[ "$state" == "running" ]]; then
            log "Stopping $CONTAINER"
            docker stop "$CONTAINER" >/dev/null
        else
            log "$CONTAINER is already $state"
        fi
        ;;
    reset)
        log "Removing $CONTAINER and volume $VOLUME"
        docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
        docker volume rm "$VOLUME" >/dev/null 2>&1 || true
        log "Removed. Re-run without --reset to create a fresh instance."
        ;;
    start)
        if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
            log "Pulling $IMAGE"
            docker pull "$IMAGE"
        fi
        state="$(container_state)"
        if [[ "$state" == "running" ]]; then
            log "$CONTAINER is already running"
        elif [[ -n "$state" ]]; then
            log "Starting existing $CONTAINER"
            docker start "$CONTAINER" >/dev/null
            wait_healthy
        else
            log "Creating $CONTAINER from $IMAGE"
            docker volume create "$VOLUME" >/dev/null
            docker run -d \
                --name "$CONTAINER" \
                --restart unless-stopped \
                -p "${BIND}:5432" \
                -e "POSTGRES_USER=${USER_NAME}" \
                -e "POSTGRES_PASSWORD=${PASSWORD}" \
                -e "POSTGRES_DB=${DATABASE}" \
                -v "${VOLUME}:/var/lib/postgresql/data" \
                --health-cmd="pg_isready -U ${USER_NAME} -d ${DATABASE}" \
                --health-interval=5s \
                --health-timeout=5s \
                --health-retries=12 \
                "$IMAGE" >/dev/null
            wait_healthy
        fi
        print_status
        ;;
esac
