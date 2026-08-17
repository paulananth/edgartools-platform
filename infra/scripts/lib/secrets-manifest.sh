#!/usr/bin/env bash
# secrets-manifest.sh
#
# Shared helper for populating scripts to look up a declared secret's name
# from ../secrets-manifest.json, instead of each script independently
# hardcoding the same name string (credential-isolation architecture
# review, Candidate 2). secrets_manifest_name() is a presence check, not a
# rename/mapping mechanism: it returns its input unchanged when the name is
# declared, and fails loudly when it isn't -- so a typo or a manifest/script
# drift is caught immediately instead of silently writing to an undeclared
# secret id.
#
# Usage (from a script that also sets SCRIPT_DIR):
#   source "${SCRIPT_DIR}/lib/secrets-manifest.sh"
#   SECRET_ID="${SECRET_ID:-${NAME_PREFIX}/$(secrets_manifest_name "mdm/postgres_dsn")}" || exit 1
#
# Deliberately no `set -euo pipefail` here, unlike every executable script in
# this directory: this file is always sourced, never run directly, and a
# sourced file mutating the caller's shell options is its own surprise.
# Callers already set their own -euo pipefail; secrets_manifest_name()'s
# explicit `return 1` + `|| exit 1` at each call site is what enforces
# failure here, independent of the caller's options.

SECRETS_MANIFEST_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_MANIFEST_PATH="${SECRETS_MANIFEST_PATH:-${SECRETS_MANIFEST_LIB_DIR}/../secrets-manifest.json}"

secrets_manifest_name() {
  local key="${1:?secrets_manifest_name requires a secret name, e.g. mdm/postgres_dsn}"

  command -v jq >/dev/null 2>&1 || {
    echo "ERROR: jq is required to read ${SECRETS_MANIFEST_PATH}" >&2
    return 1
  }
  [[ -f "$SECRETS_MANIFEST_PATH" ]] || {
    echo "ERROR: secrets manifest not found at ${SECRETS_MANIFEST_PATH}" >&2
    return 1
  }

  local resolved
  resolved="$(jq -r --arg key "$key" '.secrets[]? | select(.name == $key) | .name' "$SECRETS_MANIFEST_PATH")"
  if [[ -z "$resolved" ]]; then
    echo "ERROR: '${key}' is not declared in ${SECRETS_MANIFEST_PATH} -- add it there first" >&2
    return 1
  fi
  echo "$resolved"
}
