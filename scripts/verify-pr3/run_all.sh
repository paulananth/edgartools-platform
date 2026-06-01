#!/usr/bin/env bash
# Run all PR-3 verification stages.
#
# Stage 1 (offline, authoritative): Step Function Branch B structural integrity.
#   Extracts write_load_history_definition() from the deploy script, runs it with
#   placeholder ARNs (JSON-only, no AWS calls), and validates the Stage1Parallel
#   ASL — the two-branch fundamentals/ownership split (PR-3's one real gap).
#
# Stage 2 (offline gate + best-effort run): bootstrap-fundamentals CLI + windowing.
#   The offline gate is deterministic (no network); the per-filing run is
#   best-effort and skipped gracefully on network/MDM/bronze constraints.

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/00_lib.sh"

SCRIPTS_DIR="$(dirname "${BASH_SOURCE[0]}")"

step "Running PR-3 verification ($(date -u +%Y-%m-%dT%H:%M:%SZ))"

OVERALL_FAIL=0
for stage in 01_check_sfn_branch_b.sh 02_smoke_bootstrap_fundamentals.sh; do
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
    printf '%s[VERIFY-PR3 ALL OK]%s\n' "${C_GREEN}" "${C_RESET}" >&2
    exit 0
else
    printf '%s[VERIFY-PR3 STOPPED]%s\n' "${C_RED}" "${C_RESET}" >&2
    exit 1
fi
