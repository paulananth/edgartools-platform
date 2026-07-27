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
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
CONNECTION="${SNOW_CONNECTION:-edgartools-dev}"
DATABASE="${DASHBOARD_DATABASE:-EDGARTOOLS_DEV}"
SCHEMA="${DASHBOARD_SCHEMA:-EDGARTOOLS_DASHBOARD}"
STAGE="${DASHBOARD_STAGE:-DASHBOARD_SRC}"
STAGE_FQN="${DATABASE}.${SCHEMA}.${STAGE}"

echo "Uploading Streamlit files to @${STAGE_FQN} via connection '${CONNECTION}'"

# Stage from a temp dir, not SCRIPT_DIR, so a generated copy never sits in
# (or risks being committed from) the tracked source tree if this script
# dies mid-run. `mktemp -d` (no suffix) avoids the BSD/GNU mktemp mismatch
# documented in CLAUDE.md's AWS-teardown 5-whys.
STAGING_DIR="$(mktemp -d)"
trap 'rm -rf "${STAGING_DIR}"' EXIT

cp "${SCRIPT_DIR}/streamlit_app.py" "${STAGING_DIR}/streamlit_app.py"
cp "${SCRIPT_DIR}/environment.yml" "${STAGING_DIR}/environment.yml"

# GH-246: dashboard_modes.py is the single authoritative Agent View/Explore
# mode policy (edgar_warehouse/serving/dashboard_modes.py, unit-tested).
# Staged here byte-identical -- not hand-copied -- so the SiS runtime (which
# has no edgar_warehouse package installed) imports the same source file
# every other caller in the repo imports.
DASHBOARD_MODES_SRC="${REPO_ROOT}/edgar_warehouse/serving/dashboard_modes.py"
if [[ ! -f "${DASHBOARD_MODES_SRC}" ]]; then
  echo "Missing source file: ${DASHBOARD_MODES_SRC}" >&2
  exit 1
fi
cp "${DASHBOARD_MODES_SRC}" "${STAGING_DIR}/dashboard_modes.py"

for file in streamlit_app.py dashboard_modes.py environment.yml; do
  src_path="${STAGING_DIR}/${file}"
  # Snow CLI on Windows runs as a native exe and rejects Git Bash MSYS paths
  # like /c/Users/... — convert to a forward-slash absolute path snow accepts.
  if command -v cygpath >/dev/null 2>&1; then
    src_path_native="$(cygpath -m "${src_path}")"
  else
    src_path_native="${src_path}"
  fi
  # Convert backslashes to forward slashes for file:// URI compatibility.
  src_uri="file://${src_path_native//\\//}"
  snow sql --connection "${CONNECTION}" --stdin <<SQL
PUT ${src_uri} @${STAGE_FQN}
    AUTO_COMPRESS=FALSE
    OVERWRITE=TRUE;
SQL
done

echo "Done. Open Snowsight → Streamlit → ${DATABASE}.${SCHEMA}.EDGARTOOLS_DASHBOARD"
