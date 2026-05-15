#!/usr/bin/env bash
# Wrapper: install missing deps then run verify-counts.py
#
# Usage:
#   ./scripts/ops/verify-counts.sh
#   ./scripts/ops/verify-counts.sh --skip-silver          # skip the 400MB download
#   ./scripts/ops/verify-counts.sh --silver-local /tmp/silver-dev.duckdb
#   ./scripts/ops/verify-counts.sh --skip-mdm --skip-neo4j  # gold only

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
uv pip install --quiet duckdb psycopg2-binary neo4j 2>/dev/null || true
uv run python3 "${SCRIPT_DIR}/verify-counts.py" "$@"
