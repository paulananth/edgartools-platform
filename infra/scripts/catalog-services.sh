#!/usr/bin/env bash
set -euo pipefail

# Start or stop this repository's local OpenMetadata and sibling AutoOntology.
# Credentials stay in the two private .env files; this script never sources or prints them.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
platform_env="${OPENMETADATA_ENV_FILE:-$repo_root/.env}"
auto_root="${AUTO_ONTOLOGY_DIR:-$repo_root/../auto-ontology}"
auto_env="$auto_root/.env"
om_compose="$repo_root/infra/openmetadata/docker-compose.yml"
ao_compose="$auto_root/docker-compose.yml"

[[ -f "$auto_env" ]] || { echo "missing AutoOntology env: $auto_env" >&2; exit 2; }
[[ -f "$om_compose" ]] || { echo "missing OpenMetadata compose file" >&2; exit 2; }
[[ -f "$ao_compose" ]] || { echo "missing AutoOntology compose file" >&2; exit 2; }

case "${1:-}" in
  sync-auto)
    : "${CATALOG_OWNER_ENV:?Set the private migration-role environment file path}"
    uv run --no-project --with 'psycopg[binary]' python "$repo_root/skills/auto-ontology/scripts/catalog-readers.py" \
      --config "${CATALOG_SOURCES_CONFIG:-$repo_root/infra/catalog-sources.json}" \
      --owner-env "$CATALOG_OWNER_ENV" \
      --reader-env "${CATALOG_READER_ENV:-$HOME/.local/share/edgartools/auto-ontology/reader.env}" \
      --auto-env "$auto_env"
    docker compose --env-file "$auto_env" -f "$ao_compose" up -d --wait --wait-timeout 180 --no-build --no-deps \
      --force-recreate auto-ontology ingestion-service auto-ontology-frontend
    ;;
  start)
    [[ -f "$platform_env" ]] || { echo "missing platform env" >&2; exit 2; }
    docker compose --env-file "$platform_env" -p edgartools-openmetadata \
      -f "$om_compose" up -d --wait
    docker compose --env-file "$auto_env" -f "$ao_compose" up -d --build
    ;;
  stop)
    [[ -f "$platform_env" ]] || { echo "missing platform env" >&2; exit 2; }
    docker compose --env-file "$auto_env" -f "$ao_compose" down
    docker compose --env-file "$platform_env" -p edgartools-openmetadata \
      -f "$om_compose" down
    ;;
  *)
    echo "usage: $0 start|stop|sync-auto" >&2
    exit 2
    ;;
esac
