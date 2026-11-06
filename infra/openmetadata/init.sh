#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
docker compose -f "$repo_root/infra/openmetadata/docker-compose.yml" up -d --wait --wait-timeout 1200
exec uv run --no-project python "$repo_root/skills/openmetadata/scripts/initialize.py"
