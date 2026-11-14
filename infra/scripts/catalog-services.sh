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

[[ -f "$platform_env" ]] || { echo "missing platform env: $platform_env" >&2; exit 2; }
[[ -f "$auto_env" ]] || { echo "missing AutoOntology env: $auto_env" >&2; exit 2; }
[[ -f "$om_compose" ]] || { echo "missing OpenMetadata compose file" >&2; exit 2; }
[[ -f "$ao_compose" ]] || { echo "missing AutoOntology compose file" >&2; exit 2; }

case "${1:-}" in
  start)
    docker compose --env-file "$platform_env" -p edgartools-openmetadata \
      -f "$om_compose" up -d --wait
    docker compose --env-file "$auto_env" -f "$ao_compose" up -d --build
    ;;
  stop)
    docker compose --env-file "$auto_env" -f "$ao_compose" down
    docker compose --env-file "$platform_env" -p edgartools-openmetadata \
      -f "$om_compose" down
    ;;
  *)
    echo "usage: $0 start|stop" >&2
    exit 2
    ;;
esac
