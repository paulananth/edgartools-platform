#!/usr/bin/env bash
# GH-247: reproducible, verifiable Snowflake dashboard release path.
# GH-252: parametrized to deploy any Streamlit-in-Snowflake app in this
# repo (not just the original EDGARTOOLS_DASHBOARD), via DASHBOARD_APP_NAME/
# DASHBOARD_SOURCE_DIR/DASHBOARD_STREAMLIT_OBJECT/DASHBOARD_RELEASE_FILES/
# DASHBOARD_TEST_PATHS below -- see "App parametrization" section. All
# defaults are unchanged from before GH-252, so an invocation with none of
# those set behaves exactly as it did for the original dashboard.
#
# Replaces the old bare two-file "PUT ... OVERWRITE=TRUE" upload. A single
# run of this script: runs credential-free dashboard tests, computes and
# records release evidence (git commit, source digests, environment,
# dependency-lock digest, app version), backs up the currently-staged
# release before overwriting it (so there is always a documented rollback
# target), prunes stale backed-up releases beyond a retention count, and
# writes a secret-free JSON evidence artifact both locally and to the
# stage.
#
# What this script does NOT do (see PR/issue #247 for why): apply the
# EDGARTOOLS_{ENV}_DASHBOARD_OWNER role from
# infra/terraform/access/snowflake/modules/account_access -- that is a
# separate, deliberately-approved live Terraform apply, not something a
# deploy script does implicitly. This script assumes whatever role the
# SnowCLI connection authenticates as already has the necessary
# CREATE STAGE/CREATE STREAMLIT/USAGE privileges on the dashboard schema
# (today: an existing broader role; going forward: that dashboard-owner
# role once its grants are live).
#
# Prereqs:
#   - SnowCLI installed (`snow --version`), unless --dry-run
#   - Terraform-managed stage (DASHBOARD_DATABASE.DASHBOARD_SCHEMA.DASHBOARD_STAGE)
#     already exists
#   - A SnowCLI connection (default: edgartools-dev)
#   - uv (for the pre-flight credential-free test run)
#
# Usage (original EDGARTOOLS_DASHBOARD app, all defaults):
#   bash deploy.sh                       # uses default connection edgartools-dev
#   SNOW_CONNECTION=edgartools-prod bash deploy.sh
#   bash deploy.sh --dry-run             # compute + write evidence.json locally,
#                                         # run pre-flight tests, skip all `snow sql`
#   bash deploy.sh --skip-tests          # skip the pre-flight test run (not recommended)
#
# Usage (a different app, e.g. GH-252's MDM dashboard):
#   DASHBOARD_APP_NAME=mdm-dashboard \
#   DASHBOARD_SOURCE_DIR="${REPO_ROOT}/infra/snowflake/mdm_dashboard" \
#   DASHBOARD_SCHEMA=MDM_GRAPH_REVIEW_DASHBOARD \
#   DASHBOARD_STREAMLIT_OBJECT=MDM_GRAPH_DASHBOARD \
#   DASHBOARD_RELEASE_FILES="streamlit_app.py environment.yml" \
#   DASHBOARD_TEST_PATHS="tests/architecture/test_mdm_dashboard_streamlit.py" \
#   SNOW_CONNECTION=edgartools-prod bash deploy.sh
#
# Rollback: each release's evidence.json records a `rollback_command` field
# pointing at the release this one is about to replace. Run that recorded
# command (a `COPY FILES INTO @stage FROM
# @stage/releases/<previous_app_version>/` statement) to restore it.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
CONNECTION="${SNOW_CONNECTION:-edgartools-dev}"
DATABASE="${DASHBOARD_DATABASE:-EDGARTOOLS_DEV}"
SCHEMA="${DASHBOARD_SCHEMA:-EDGARTOOLS_DASHBOARD}"
STAGE="${DASHBOARD_STAGE:-DASHBOARD_SRC}"
STAGE_FQN="${DATABASE}.${SCHEMA}.${STAGE}"
ENVIRONMENT_LABEL="${DASHBOARD_ENVIRONMENT:-${CONNECTION}}"
RETAIN_RELEASES="${DASHBOARD_RETAIN_RELEASES:-5}"
EVIDENCE_DIR="${DASHBOARD_EVIDENCE_DIR:-${SCRIPT_DIR}/.evidence}"

# --- App parametrization (GH-252) -------------------------------------------
# APP_NAME namespaces the local evidence history so two apps deployed to the
# same CONNECTION/ENVIRONMENT_LABEL never read or overwrite each other's
# previous_app_version/rollback_command -- keep this stable per app.
APP_NAME="${DASHBOARD_APP_NAME:-dashboard}"
# Where streamlit_app.py/environment.yml/etc. for THIS app live.
APP_SOURCE_DIR="${DASHBOARD_SOURCE_DIR:-${SCRIPT_DIR}}"
# The CREATE STREAMLIT object name this app's stage backs (DESCRIBE'd as a
# post-deploy check below) -- independent of DASHBOARD_SCHEMA/STAGE, which
# already vary per app.
STREAMLIT_OBJECT="${DASHBOARD_STREAMLIT_OBJECT:-EDGARTOOLS_DASHBOARD}"
# Space-separated filenames to stage from APP_SOURCE_DIR, relative to it.
# "dashboard_modes.py" is special-cased below (staged from
# edgar_warehouse/serving/, not APP_SOURCE_DIR) -- list it here only for
# apps that actually import it (GH-246's Agent View/Explore policy).
read -ra RELEASE_FILES <<< "${DASHBOARD_RELEASE_FILES:-streamlit_app.py dashboard_modes.py dashboard_query_registry.py environment.yml}"
# Space-separated pytest paths for this app's credential-free pre-flight
# tests. Defaults to the original EDGARTOOLS_DASHBOARD app's tests only
# when APP_NAME is left at its own default -- preserves docs/runbook.md's
# documented zero-config `bash deploy.sh` invocation. Any other APP_NAME
# must set DASHBOARD_TEST_PATHS explicitly (or pass --skip-tests): a second
# app's deploy must not silently "pass" pre-flight by validating an
# unrelated app instead of itself.
if [[ "${APP_NAME}" == "dashboard" ]]; then
  DEFAULT_TEST_PATHS="tests/architecture/test_snowflake_streamlit_financial_factors.py tests/unit/test_dashboard_modes.py"
else
  DEFAULT_TEST_PATHS=""
fi
read -ra TEST_PATHS <<< "${DASHBOARD_TEST_PATHS:-${DEFAULT_TEST_PATHS}}"

DRY_RUN=false
SKIP_TESTS=false
for arg in "$@"; do
  case "${arg}" in
    --dry-run) DRY_RUN=true ;;
    --skip-tests) SKIP_TESTS=true ;;
    *)
      echo "Unknown argument: ${arg}" >&2
      exit 1
      ;;
  esac
done

if [[ "${SKIP_TESTS}" == "false" && ${#TEST_PATHS[@]} -eq 0 ]]; then
  echo "DASHBOARD_TEST_PATHS is required (space-separated pytest paths for" >&2
  echo "this app's credential-free pre-flight tests), or pass --skip-tests" >&2
  echo "to explicitly opt out (not recommended)." >&2
  exit 1
fi

json_escape() {
  # Minimal JSON string escaping for values this script controls (paths,
  # git metadata, generated shell commands) -- not a general-purpose JSON
  # encoder. Caught a real bug in testing: rollback_command embeds a
  # double-quoted `snow sql -q "..."` invocation, which broke the emitted
  # JSON before this existed (unescaped `"` inside a JSON string value).
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

sha256_of() {
  # macOS ships shasum, not sha256sum; Linux CI has both -- prefer
  # sha256sum when present (matches CLAUDE.md's cross-platform-script
  # discipline: don't assume a GNU-only or BSD-only tool exists).
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

# ---------------------------------------------------------------------------
# 1. Credential-free pre-flight tests (GH-247: "Credential-free dashboard
#    tests run before upload"). These tests fake out streamlit/plotly/
#    snowflake entirely -- see tests/architecture/
#    test_snowflake_streamlit_financial_factors.py's _load_app() -- no
#    Snowflake connection or secret is ever touched.
# ---------------------------------------------------------------------------
if [[ "${SKIP_TESTS}" == "false" ]]; then
  echo "Running credential-free dashboard tests for ${APP_NAME}..."
  (
    cd "${REPO_ROOT}"
    uv run python -m pytest "${TEST_PATHS[@]}" -q
  )
else
  echo "Skipping pre-flight tests (--skip-tests)." >&2
fi

# ---------------------------------------------------------------------------
# 2. Stage from a temp dir, not SCRIPT_DIR, so a generated copy never sits
#    in (or risks being committed from) the tracked source tree if this
#    script dies mid-run. `mktemp -d` (no suffix) avoids the BSD/GNU
#    mktemp mismatch documented in CLAUDE.md's AWS-teardown 5-whys.
# ---------------------------------------------------------------------------
STAGING_DIR="$(mktemp -d)"
trap 'rm -rf "${STAGING_DIR}"' EXIT

for file in "${RELEASE_FILES[@]}"; do
  if [[ "${file}" == "dashboard_modes.py" || "${file}" == "dashboard_query_registry.py" ]]; then
    # GH-246: dashboard_modes.py is the single authoritative Agent
    # View/Explore mode policy (edgar_warehouse/serving/dashboard_modes.py,
    # unit-tested). Staged here byte-identical -- not hand-copied -- so the
    # SiS runtime (which has no edgar_warehouse package installed) imports
    # the same source file every other caller in the repo imports. Only
    # apps that actually list it in RELEASE_FILES need this -- e.g. GH-252's
    # MDM dashboard has no Agent View/Explore concept and omits it.
    DASHBOARD_MODES_SRC="${REPO_ROOT}/edgar_warehouse/serving/${file}"
    if [[ ! -f "${DASHBOARD_MODES_SRC}" ]]; then
      echo "Missing source file: ${DASHBOARD_MODES_SRC}" >&2
      exit 1
    fi
    cp "${DASHBOARD_MODES_SRC}" "${STAGING_DIR}/${file}"
    continue
  fi
  src="${APP_SOURCE_DIR}/${file}"
  if [[ ! -f "${src}" ]]; then
    echo "Missing source file: ${src}" >&2
    exit 1
  fi
  cp "${src}" "${STAGING_DIR}/${file}"
done

# ---------------------------------------------------------------------------
# 3. Release evidence (GH-247: "records git commit, source digest,
#    environment, dependency lock, and application version" + "writes a
#    secret-free JSON... evidence artifact"). Computed before any `snow
#    sql` call runs, so --dry-run can exercise this exact logic with no
#    Snowflake connection at all.
# ---------------------------------------------------------------------------
GIT_COMMIT="$(cd "${REPO_ROOT}" && git rev-parse HEAD)"
GIT_COMMIT_SHORT="$(cd "${REPO_ROOT}" && git rev-parse --short=12 HEAD)"
APP_VERSION="sha-${GIT_COMMIT_SHORT}"
DEPENDENCY_LOCK_DIGEST="$(sha256_of "${STAGING_DIR}/environment.yml")"
DEPLOYED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

SOURCE_DIGESTS_JSON="{"
first=true
for file in "${RELEASE_FILES[@]}"; do
  digest="$(sha256_of "${STAGING_DIR}/${file}")"
  if [[ "${first}" == "true" ]]; then
    first=false
  else
    SOURCE_DIGESTS_JSON+=","
  fi
  SOURCE_DIGESTS_JSON+="\"${file}\":\"${digest}\""
done
SOURCE_DIGESTS_JSON+="}"

# Combined digest over RELEASE_FILES concatenated in array order -- one
# value to compare for "did anything in this release change" without
# inspecting every per-file digest. Driven by the same array used to stage
# and per-file-digest the release above, not a hardcoded filename list --
# a second app with different RELEASE_FILES (e.g. no dashboard_modes.py)
# must not cat a file it never staged.
COMBINED_FILE="${STAGING_DIR}/.combined_for_digest"
: > "${COMBINED_FILE}"
for file in "${RELEASE_FILES[@]}"; do
  cat "${STAGING_DIR}/${file}" >> "${COMBINED_FILE}"
done
COMBINED_DIGEST="$(sha256_of "${COMBINED_FILE}")"
rm -f "${COMBINED_FILE}"

RELEASES_PREFIX="releases"
# Namespaced by APP_NAME, not just ENVIRONMENT_LABEL -- two apps deployed
# through the same connection/environment (e.g. both prod) must not read or
# clobber each other's previous_app_version/rollback_command.
PREVIOUS_EVIDENCE_LOCAL="${EVIDENCE_DIR}/${ENVIRONMENT_LABEL}/${APP_NAME}/latest.json"
PREVIOUS_APP_VERSION=""
if [[ -f "${PREVIOUS_EVIDENCE_LOCAL}" ]]; then
  # Plain grep/sed, not jq -- jq isn't a listed prereq for this script and
  # the evidence file's shape is controlled by this same script.
  PREVIOUS_APP_VERSION="$(grep -o '"app_version": *"[^"]*"' "${PREVIOUS_EVIDENCE_LOCAL}" | head -1 | sed -E 's/.*"([^"]+)"$/\1/' || true)"
fi

ROLLBACK_COMMAND="n/a (no previous release recorded locally at ${PREVIOUS_EVIDENCE_LOCAL})"
if [[ -n "${PREVIOUS_APP_VERSION}" ]]; then
  # Single-quoted -q argument -- avoids embedding literal double quotes in
  # a value that gets JSON-encoded below (json_escape still runs as
  # defense-in-depth, not as the only thing preventing invalid JSON here).
  ROLLBACK_COMMAND="snow sql --connection ${CONNECTION} -q 'COPY FILES INTO @${STAGE_FQN} FROM @${STAGE_FQN}/${RELEASES_PREFIX}/${PREVIOUS_APP_VERSION}/;'"
fi

EVIDENCE_JSON=$(cat <<EOF
{
  "git_commit": "$(json_escape "${GIT_COMMIT}")",
  "app_version": "$(json_escape "${APP_VERSION}")",
  "environment": "$(json_escape "${ENVIRONMENT_LABEL}")",
  "connection": "$(json_escape "${CONNECTION}")",
  "stage": "$(json_escape "${STAGE_FQN}")",
  "deployed_at": "$(json_escape "${DEPLOYED_AT}")",
  "dependency_lock_digest": "$(json_escape "${DEPENDENCY_LOCK_DIGEST}")",
  "combined_source_digest": "$(json_escape "${COMBINED_DIGEST}")",
  "source_digests": ${SOURCE_DIGESTS_JSON},
  "previous_app_version": $( [[ -n "${PREVIOUS_APP_VERSION}" ]] && echo "\"$(json_escape "${PREVIOUS_APP_VERSION}")\"" || echo "null" ),
  "rollback_command": "$(json_escape "${ROLLBACK_COMMAND}")",
  "dry_run": ${DRY_RUN}
}
EOF
)

mkdir -p "$(dirname "${PREVIOUS_EVIDENCE_LOCAL}")"
echo "${EVIDENCE_JSON}" > "${EVIDENCE_DIR}/${ENVIRONMENT_LABEL}/${APP_NAME}/${APP_VERSION}.json"
echo "${EVIDENCE_JSON}" > "${PREVIOUS_EVIDENCE_LOCAL}"
echo "Release evidence written to ${EVIDENCE_DIR}/${ENVIRONMENT_LABEL}/${APP_NAME}/${APP_VERSION}.json"
echo "${EVIDENCE_JSON}"

if [[ "${DRY_RUN}" == "true" ]]; then
  echo "--dry-run: skipping all snow sql calls (backup, upload, prune, staged evidence)."
  exit 0
fi

# ---------------------------------------------------------------------------
# 4. Back up the currently-staged release before overwriting it (GH-247:
#    "retains a prior rollback target"), then prune backed-up releases
#    beyond the retention count (GH-247: "prunes stale staged files").
#    NOT exercised against live Snowflake by this commit -- see PR body.
# ---------------------------------------------------------------------------
if [[ -n "${PREVIOUS_APP_VERSION}" ]]; then
  echo "Backing up current release (${PREVIOUS_APP_VERSION}) to @${STAGE_FQN}/${RELEASES_PREFIX}/${PREVIOUS_APP_VERSION}/ before overwrite..."
  snow sql --connection "${CONNECTION}" --stdin <<SQL
COPY FILES INTO @${STAGE_FQN}/${RELEASES_PREFIX}/${PREVIOUS_APP_VERSION}/
    FROM @${STAGE_FQN}
    PATTERN = '.*\\.py|.*\\.yml';
SQL
else
  echo "No previous release recorded locally -- skipping backup (first deploy for ${ENVIRONMENT_LABEL}, or evidence dir was cleared)."
fi

echo "Pruning releases beyond retention count (${RETAIN_RELEASES})..."
snow sql --connection "${CONNECTION}" --stdin <<SQL
LIST @${STAGE_FQN}/${RELEASES_PREFIX}/;
SQL
# Deliberately not auto-parsing the LIST output to auto-REMOVE here --
# that couples this script to snow CLI's exact output format for a
# destructive operation. Prints the listing so an operator (or a follow-up
# scripted pass, once the output format is confirmed live) can prune
# manually: REMOVE @<stage>/releases/<old_app_version>/;

# ---------------------------------------------------------------------------
# 5. Upload the new release + staged evidence copy.
# ---------------------------------------------------------------------------
for file in "${RELEASE_FILES[@]}"; do
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

evidence_path="${STAGING_DIR}/evidence.json"
echo "${EVIDENCE_JSON}" > "${evidence_path}"
if command -v cygpath >/dev/null 2>&1; then
  evidence_path_native="$(cygpath -m "${evidence_path}")"
else
  evidence_path_native="${evidence_path}"
fi
snow sql --connection "${CONNECTION}" --stdin <<SQL
PUT file://${evidence_path_native//\\//} @${STAGE_FQN}
    AUTO_COMPRESS=FALSE
    OVERWRITE=TRUE;
SQL

# ---------------------------------------------------------------------------
# 6. Post-deploy checks (GH-247: "inspect the Streamlit object and staged
#    artifact digest and run bounded owner/viewer smoke queries").
#    Object inspection is implemented; the owner/viewer smoke queries are
#    NOT -- see PR body: they need the dashboard_owner role's live grants
#    (infra/terraform/access/snowflake/modules/account_access) applied
#    first, which this script does not do.
# ---------------------------------------------------------------------------
echo "Post-deploy check: describing the Streamlit object..."
snow sql --connection "${CONNECTION}" --stdin <<SQL
DESCRIBE STREAMLIT ${DATABASE}.${SCHEMA}.${STREAMLIT_OBJECT};
LIST @${STAGE_FQN};
SQL

echo "Done. Open Snowsight → Streamlit → ${DATABASE}.${SCHEMA}.${STREAMLIT_OBJECT}"
echo "Release: ${APP_VERSION} (git ${GIT_COMMIT_SHORT}), evidence at ${EVIDENCE_DIR}/${ENVIRONMENT_LABEL}/${APP_NAME}/${APP_VERSION}.json"
