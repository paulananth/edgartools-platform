#!/usr/bin/env bash
# Shared helpers sourced by every PR-3 verification script.
# Strict mode and pretty logging — match the existing infra/scripts/ convention.

set -euo pipefail
IFS=$'\n\t'

# Colors only if stdout is a TTY (so logs in CI stay readable)
if [[ -t 1 ]]; then
    C_GREEN=$'\e[32m'
    C_RED=$'\e[31m'
    C_YELLOW=$'\e[33m'
    C_BLUE=$'\e[36m'
    C_BOLD=$'\e[1m'
    C_RESET=$'\e[0m'
else
    C_GREEN=""
    C_RED=""
    C_YELLOW=""
    C_BLUE=""
    C_BOLD=""
    C_RESET=""
fi

# Pass/fail counters — each script tracks its own.
PASS_COUNT=0
FAIL_COUNT=0

# Repo root — assume scripts run from any cwd; resolve via this file's dir.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." &> /dev/null && pwd)"

# ────────────────────────────────────────────────────────────────────
# Output helpers
# ────────────────────────────────────────────────────────────────────

step() {
    printf '\n%s── %s ──%s\n' "${C_BOLD}" "$*" "${C_RESET}" >&2
}

log() {
    printf '%s[verify-pr3]%s %s\n' "${C_BLUE}" "${C_RESET}" "$*" >&2
}

ok() {
    printf '  %s✓%s %s\n' "${C_GREEN}" "${C_RESET}" "$*" >&2
    PASS_COUNT=$((PASS_COUNT + 1))
}

fail_check() {
    printf '  %s✗%s %s\n' "${C_RED}" "${C_RESET}" "$*" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

warn() {
    printf '  %s!%s %s\n' "${C_YELLOW}" "${C_RESET}" "$*" >&2
}

fatal() {
    printf '%s[verify-pr3 FATAL]%s %s\n' "${C_RED}" "${C_RESET}" "$*" >&2
    exit 2
}

# ────────────────────────────────────────────────────────────────────
# Summary printer — call at the end of each stage script
# ────────────────────────────────────────────────────────────────────

print_summary() {
    local stage_name="$1"
    local total=$((PASS_COUNT + FAIL_COUNT))
    printf '\n' >&2
    if [[ $FAIL_COUNT -eq 0 ]]; then
        printf '%s%s[STAGE %s OK]%s %d/%d checks passed\n' \
            "${C_BOLD}" "${C_GREEN}" "$stage_name" "${C_RESET}" "$PASS_COUNT" "$total" >&2
        return 0
    else
        printf '%s%s[STAGE %s FAILED]%s %d/%d checks passed, %d failures\n' \
            "${C_BOLD}" "${C_RED}" "$stage_name" "${C_RESET}" \
            "$PASS_COUNT" "$total" "$FAIL_COUNT" >&2
        return 1
    fi
}

# ────────────────────────────────────────────────────────────────────
# Common assertions
# ────────────────────────────────────────────────────────────────────

# require_command <cmd> — bail out if a required tool is missing.
require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        fatal "required command not found: $1"
    fi
}

# require_file <path> — bail out if a required file is missing.
require_file() {
    if [[ ! -f "$1" ]]; then
        fatal "required file not found: $1"
    fi
}

# require_env <var-name> — bail out if a required env var is not set or empty.
require_env() {
    local var_name="$1"
    if [[ -z "${!var_name:-}" ]]; then
        fatal "required env var not set: $var_name"
    fi
}

# ────────────────────────────────────────────────────────────────────
# PR-3 specific: pick a Python runner (prefer uv, fall back to python3)
# ────────────────────────────────────────────────────────────────────

# py_run <args...> — run Python via `uv run python` if uv is available
# (resolves the project venv + editable install), otherwise plain python3.
py_run() {
    if command -v uv >/dev/null 2>&1; then
        (cd "${REPO_ROOT}" && uv run python "$@")
    elif command -v python3 >/dev/null 2>&1; then
        python3 "$@"
    else
        fatal "no Python interpreter found (need uv or python3)"
    fi
}
