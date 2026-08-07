#!/usr/bin/env bash
# install-neo4j-graph-app.sh
#
# Installs the Neo4j Graph Analytics Native App into a Snowflake account.
#
# Implements the stage added by wayfinder ticket 05 of the
# snowflake-env-provisioning map. Until now nothing in this repo installed the
# app: infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql only GRANTs
# against an application it assumes already exists, so install.sh silently
# depended on someone having installed it out of band. That assumption does not
# hold for a brand-new account, which is the case this map exists to serve.
#
# One step here is NOT scriptable, established by wayfinder ticket 02's research
# against Snowflake's primary docs: an ORGADMIN must accept the Snowflake
# Provider and Consumer Terms once per *organization*, in Snowsight (Admin »
# Terms), before any Marketplace listing can be installed. There is no
# documented SQL or API equivalent. This script therefore fails with an
# actionable message pointing at that step rather than pretending to do it.
#
# The listing is resolved at run time rather than hardcoded. Ticket 02 surfaced
# a global name (GZTDZH40CN) but flagged it explicitly unverified -- it was
# transcribed from a URL embedded in a Snowflake guide, not read off a
# SHOW AVAILABLE LISTINGS result -- and recommended runtime resolution so the
# value cannot drift or carry a transcription error.
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  install-neo4j-graph-app.sh --snow-connection <name> [options]

Required:
  --snow-connection <name>       SnowCLI connection name.

Options:
  --app-name <name>              Application name to create.
                                 Default: Neo4j_Graph_Analytics (the name
                                 infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql
                                 grants against -- change both together).
  --listing-global-name <name>   Skip resolution and install this listing
                                 directly. Use when resolution is ambiguous or
                                 the account cannot list the Marketplace.
  --listing-search <pattern>     Pattern used to resolve the listing.
                                 Default: %Graph Analytics%
  --dry-run                      Print what would run without changing anything.

Prerequisite that cannot be scripted (once per organization):
  An ORGADMIN must accept the Snowflake Provider and Consumer Terms in
  Snowsight (Admin » Terms). Until that is done, no Marketplace listing --
  including this one -- can be installed from SQL or the UI.
USAGE
}

SNOW_CONNECTION=""
APP_NAME="Neo4j_Graph_Analytics"
LISTING_GLOBAL_NAME=""
LISTING_SEARCH="%Graph Analytics%"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --snow-connection) SNOW_CONNECTION="${2:?}"; shift 2 ;;
    --app-name) APP_NAME="${2:?}"; shift 2 ;;
    --listing-global-name) LISTING_GLOBAL_NAME="${2:?}"; shift 2 ;;
    --listing-search) LISTING_SEARCH="${2:?}"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

log() { echo "==> $*" >&2; }
fail() { echo "ERROR: $*" >&2; exit 1; }

[[ -n "$SNOW_CONNECTION" ]] || { echo "ERROR: --snow-connection is required" >&2; usage >&2; exit 2; }

snow_json() {
  snow sql --connection "$SNOW_CONNECTION" --format json -q "$1" 2>/dev/null
}

terms_hint() {
  cat >&2 <<HINT

This is the manual, once-per-organization step that cannot be scripted
(wayfinder ticket 02): sign in to Snowsight as ORGADMIN, go to
Admin » Terms, and accept the Snowflake Provider and Consumer Terms.
Snowflake documents no SQL or API equivalent. Re-run this script afterward.

If the terms are already accepted, check the simpler causes first: this hint
is also printed when the connection name itself is wrong or unreachable, since
a broken connection and an unavailable listing are indistinguishable here.
Confirm with: snow sql --connection <name> -q 'SELECT CURRENT_ACCOUNT()'
HINT
}

# --- Idempotency -------------------------------------------------------------
# Re-running install.sh must not fail on an already-installed app. Checked
# first so the expensive/permission-sensitive listing resolution is skipped
# entirely on the common re-run path.
log "Checking whether application ${APP_NAME} already exists"
if EXISTING="$(snow_json "SHOW APPLICATIONS LIKE '${APP_NAME}'")" \
   && printf '%s' "$EXISTING" | python3 -c "import json,sys; sys.exit(0 if json.load(sys.stdin) else 1)" 2>/dev/null; then
  log "Application ${APP_NAME} is already installed; nothing to do."
  exit 0
fi

# --- Resolve the listing -----------------------------------------------------
if [[ -z "$LISTING_GLOBAL_NAME" ]]; then
  log "Resolving Marketplace listing matching '${LISTING_SEARCH}'"
  LISTINGS_JSON="$(snow_json "SHOW AVAILABLE LISTINGS LIKE '${LISTING_SEARCH}'")" || LISTINGS_JSON=""

  if [[ -z "$LISTINGS_JSON" ]]; then
    echo "ERROR: could not list available Marketplace listings via connection '${SNOW_CONNECTION}'." >&2
    echo "       This is the expected failure when the organization has not accepted" >&2
    echo "       the Marketplace terms, or the role lacks privileges to browse listings." >&2
    terms_hint
    exit 1
  fi

  # `SHOW AVAILABLE LISTINGS` column naming differs across Snowflake versions,
  # so match the global-name column case-insensitively rather than assuming one
  # spelling. Ambiguity is reported, never silently resolved to the first hit --
  # installing the wrong Native App is not something to guess at.
  RESOLVED="$(printf '%s' "$LISTINGS_JSON" | python3 -c '
import json, sys

rows = json.load(sys.stdin)
def pick(row, *names):
    for key, value in row.items():
        if key.lower().replace(" ", "_") in names:
            return value
    return None

found = []
for row in rows:
    name = pick(row, "global_name", "globalname")
    title = pick(row, "title", "name", "listing_name") or ""
    if name:
        found.append((name, title))

if not found:
    print("NONE")
elif len(found) > 1:
    print("AMBIGUOUS")
    for name, title in found:
        print(f"{name}\t{title}")
else:
    print("OK")
    print(f"{found[0][0]}\t{found[0][1]}")
')"

  case "$(printf '%s' "$RESOLVED" | head -1)" in
    NONE)
      echo "ERROR: no Marketplace listing matched '${LISTING_SEARCH}' for connection '${SNOW_CONNECTION}'." >&2
      echo "       If the organization has accepted the Marketplace terms, the listing may" >&2
      echo "       be titled differently -- retry with --listing-search, or pass the global" >&2
      echo "       name directly with --listing-global-name." >&2
      terms_hint
      exit 1
      ;;
    AMBIGUOUS)
      echo "ERROR: '${LISTING_SEARCH}' matched more than one listing. Re-run with an exact" >&2
      echo "       --listing-global-name (or a narrower --listing-search). Candidates:" >&2
      printf '%s\n' "$RESOLVED" | tail -n +2 | sed 's/^/         /' >&2
      exit 1
      ;;
    OK)
      LISTING_GLOBAL_NAME="$(printf '%s' "$RESOLVED" | sed -n '2p' | cut -f1)"
      LISTING_TITLE="$(printf '%s' "$RESOLVED" | sed -n '2p' | cut -f2)"
      log "Resolved listing: ${LISTING_GLOBAL_NAME} (${LISTING_TITLE})"
      ;;
    *)
      fail "unexpected listing-resolution output: $(printf '%s' "$RESOLVED" | head -1)"
      ;;
  esac
else
  log "Using operator-supplied listing global name: ${LISTING_GLOBAL_NAME}"
fi

# --- Install -----------------------------------------------------------------
# BACKGROUND_INSTALL is deliberately not used: install.sh runs its stages
# sequentially and the grants stage later in the run needs the application to
# actually exist, so a non-blocking install would just move the failure.
INSTALL_SQL="CREATE APPLICATION ${APP_NAME} FROM LISTING '${LISTING_GLOBAL_NAME}';"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[dry-run] ${INSTALL_SQL}"
  echo "[dry-run] SHOW APPLICATIONS LIKE '${APP_NAME}';"
  exit 0
fi

log "Installing ${APP_NAME} from listing ${LISTING_GLOBAL_NAME}"
if ! snow sql --connection "$SNOW_CONNECTION" -q "$INSTALL_SQL"; then
  echo "ERROR: CREATE APPLICATION failed." >&2
  echo "       Requires CREATE APPLICATION on the account (plus IMPORT SHARE when" >&2
  echo "       installing across accounts), and the organization-level terms below." >&2
  terms_hint
  exit 1
fi

# Confirm rather than trusting the statement's exit code: the grants stage that
# runs later in install.sh depends on this object existing.
log "Verifying ${APP_NAME} is present"
VERIFY_JSON="$(snow_json "SHOW APPLICATIONS LIKE '${APP_NAME}'")" || VERIFY_JSON=""
printf '%s' "$VERIFY_JSON" | python3 -c "import json,sys; sys.exit(0 if json.load(sys.stdin) else 1)" 2>/dev/null \
  || fail "${APP_NAME} was not found after CREATE APPLICATION reported success."

log "${APP_NAME} installed."
