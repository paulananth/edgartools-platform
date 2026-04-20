#!/usr/bin/env bash
# Upload the Streamlit app source files to the dashboard stage.
#
# Prereqs:
#   - SnowCLI installed (`snow --version`)
#   - Terraform-managed stage `EDGARTOOLS_DASHBOARD.DASHBOARD_SRC` already exists
#   - A SnowCLI connection (default: edgartools-dev)
#
# Usage:
#   bash deploy.sh                       # uses default connection edgartools-dev
#   SNOW_CONNECTION=edgartools-prod bash deploy.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONNECTION="${SNOW_CONNECTION:-edgartools-dev}"
DATABASE="${DASHBOARD_DATABASE:-EDGARTOOLS_DEV}"
SCHEMA="${DASHBOARD_SCHEMA:-EDGARTOOLS_DASHBOARD}"
STAGE="${DASHBOARD_STAGE:-DASHBOARD_SRC}"
STAGE_FQN="${DATABASE}.${SCHEMA}.${STAGE}"

echo "Uploading Streamlit files to @${STAGE_FQN} via connection '${CONNECTION}'"

for file in streamlit_app.py environment.yml; do
  src_path="${SCRIPT_DIR}/${file}"
  if [[ ! -f "${src_path}" ]]; then
    echo "Missing source file: ${src_path}" >&2
    exit 1
  fi
  # Convert Windows backslashes to forward slashes for file:// URI
  src_uri="file://${src_path//\\//}"
  snow sql --connection "${CONNECTION}" --stdin <<SQL
PUT ${src_uri} @${STAGE_FQN}
    AUTO_COMPRESS=FALSE
    OVERWRITE=TRUE;
SQL
done

echo "Done. Open Snowsight → Streamlit → ${DATABASE}.${SCHEMA}.EDGARTOOLS_DASHBOARD"
