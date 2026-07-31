#!/usr/bin/env bash
# Runs the two real acceptance suites against the already-deployed production app.
set -euo pipefail

: "${SNOW_CONNECTION:?Set SNOW_CONNECTION (for example edgartools-prod)}"
: "${DASHBOARD_DATABASE:=EDGARTOOLS_PROD}"

uv run scripts/test/dashboard-subject-contract.py \
  --connection "${SNOW_CONNECTION}" --database "${DASHBOARD_DATABASE}"
npx --yes playwright install chromium
npx --yes -p playwright node scripts/test/dashboard-browser-e2e.mjs
