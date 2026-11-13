#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="${OPENMETADATA_ENV_FILE:-$repo_root/.env}"
unset OPENMETADATA_URL OPENMETADATA_LOGIN_EMAIL OPENMETADATA_LOGIN_PASSWORD
unset OPENMETADATA_PASSWORD OPENMETADATA_PASSWORD_CHANGED OPENMETADATA_TOKEN
unset OPENMETADATA_HOST_PORT OPENMETADATA_COMPOSE_PROJECT
if [[ -f "$env_file" ]]; then
  chmod 600 "$env_file"
  set -a
  # The private runtime file is shell-compatible KEY=VALUE configuration.
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
fi
expected_url="http://127.0.0.1:8587"
if [[ -n "${OPENMETADATA_URL:-}" && "${OPENMETADATA_URL%/}" != "$expected_url" ]]; then
  echo "OpenMetadata .env must target this local instance at 127.0.0.1:8587" >&2
  exit 2
fi
export OPENMETADATA_URL="$expected_url"
export OPENMETADATA_HOST_PORT=8587
compose_project=edgartools-openmetadata

docker compose -p "$compose_project" -f "$repo_root/infra/openmetadata/docker-compose.yml" up -d --wait --wait-timeout 1200
uv run --no-project python "$repo_root/infra/openmetadata/credentials.py" --env-file "$env_file"
if [[ -f "$env_file" ]]; then
  set -a
  # Refresh the shell with the token just written by credentials.py.
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
fi
exec uv run --no-project python "$repo_root/skills/openmetadata/scripts/initialize.py"
