#!/usr/bin/env bash
# Run all PR-1 verification stages in order, stopping on the first failure.
#
# Stages:
#   1. Local schema integrity        (no creds)
#   2. PyArrow builder smoke test    (no creds)
#   3. Snowflake DDL deployment      (creds required)
#   4. Composite-key MERGE semantics (creds required)
#
# Stage 5 (full Parquet roundtrip via gold-refresh) is NOT yet implemented
# because PR-2 (warehouse export wiring) needs to land first.

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/00_lib.sh"

SCRIPTS_DIR="$(dirname "${BASH_SOURCE[0]}")"

# Allow operator to skip stages 3/4 (the cloud ones) via --offline flag
OFFLINE=false
for arg in "$@"; do
    case "$arg" in
        --offline)
            OFFLINE=true ;;
        --help|-h)
            cat <<EOF
Usage: $0 [--offline]

  --offline   Run only stages 1 and 2 (no Snowflake creds required)
EOF
            exit 0 ;;
    esac
done

STAGES=(
    "01_check_local_schema.sh:Stage 1 — Local schema integrity"
    "02_smoke_builders.sh:Stage 2 — PyArrow builder smoke test"
)

if ! $OFFLINE; then
    STAGES+=(
        "03_check_snowflake_ddl.sh:Stage 3 — Snowflake DDL deployment"
        "04_smoke_merge_proc.sh:Stage 4 — Composite-key MERGE semantics"
    )
fi

step "Running PR-1 verification ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
log "Mode: $($OFFLINE && echo offline || echo full)"
log "${#STAGES[@]} stage(s) queued"

OVERALL_FAIL=0
for spec in "${STAGES[@]}"; do
    script="${spec%%:*}"
    label="${spec#*:}"
    printf '\n' >&2
    log "▶ ${label}"
    if bash "${SCRIPTS_DIR}/${script}"; then
        log "✓ ${label} — OK"
    else
        log "✗ ${label} — FAILED (subsequent stages skipped)"
        OVERALL_FAIL=1
        break
    fi
done

printf '\n%s' "${C_BOLD}" >&2
if [[ $OVERALL_FAIL -eq 0 ]]; then
    printf '%s[VERIFY-PR1 ALL OK]%s\n' "${C_GREEN}" "${C_RESET}" >&2
    exit 0
else
    printf '%s[VERIFY-PR1 STOPPED]%s see stage logs above\n' "${C_RED}" "${C_RESET}" >&2
    exit 1
fi
