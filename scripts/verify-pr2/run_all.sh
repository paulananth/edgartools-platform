#!/usr/bin/env bash
# Run all PR-2 verification stages (currently 2 offline stages).
# PR-2 has no cloud-dependent stages — gold-refresh runs locally; the cloud
# verification (Parquet roundtrip into Snowflake source tables) requires a
# real bootstrap-fundamentals run, which is gated by PR-3 and PR-4.

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/00_lib.sh"

SCRIPTS_DIR="$(dirname "${BASH_SOURCE[0]}")"

step "Running PR-2 verification ($(date -u +%Y-%m-%dT%H:%M:%SZ))"

OVERALL_FAIL=0
for stage in 01_check_export_wiring.sh 02_smoke_gold_refresh.sh; do
    printf '\n' >&2
    log "▶ $stage"
    if bash "${SCRIPTS_DIR}/${stage}"; then
        log "✓ $stage OK"
    else
        log "✗ $stage FAILED — subsequent stages skipped"
        OVERALL_FAIL=1
        break
    fi
done

printf '\n%s' "${C_BOLD}" >&2
if [[ $OVERALL_FAIL -eq 0 ]]; then
    printf '%s[VERIFY-PR2 ALL OK]%s\n' "${C_GREEN}" "${C_RESET}" >&2
    exit 0
else
    printf '%s[VERIFY-PR2 STOPPED]%s\n' "${C_RED}" "${C_RESET}" >&2
    exit 1
fi
