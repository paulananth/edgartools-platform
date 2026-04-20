#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  publish-warehouse-image-via-wsl.sh [--wsl-distro <name>] --aws-region <region> --ecr-repository <name> --image-tag <tag> [options]

This wrapper is the canonical local Windows publish path. Run it from Git Bash.
It re-enters WSL, bridges to the Windows Docker and AWS CLIs, forces linux publish mode,
and delegates to infra/scripts/publish-warehouse-image-wsl-bridge.sh.
EOF
}

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

gitbash_path_to_wsl() {
    local gitbash_path normalized_path drive_letter path_suffix
    gitbash_path="$1"
    normalized_path="${gitbash_path//\\//}"

    if [[ "${normalized_path}" =~ ^/([A-Za-z])/(.*)$ ]]; then
        drive_letter="$(printf '%s' "${BASH_REMATCH[1]}" | tr '[:upper:]' '[:lower:]')"
        path_suffix="${BASH_REMATCH[2]}"
        printf '/mnt/%s/%s\n' "${drive_letter}" "${path_suffix}"
        return 0
    fi

    if [[ "${normalized_path}" =~ ^([A-Za-z]):/(.*)$ ]]; then
        drive_letter="$(printf '%s' "${BASH_REMATCH[1]}" | tr '[:upper:]' '[:lower:]')"
        path_suffix="${BASH_REMATCH[2]}"
        printf '/mnt/%s/%s\n' "${drive_letter}" "${path_suffix}"
        return 0
    fi

    fail "expected Git Bash path, got: ${gitbash_path}"
}

WSL_DISTRO="${WSL_DISTRO:-Ubuntu}"
FORWARDED_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --wsl-distro)
            [[ $# -ge 2 ]] || fail "--wsl-distro requires a value"
            WSL_DISTRO="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            FORWARDED_ARGS+=("$1")
            shift
            ;;
    esac
done

command -v git >/dev/null 2>&1 || fail "git is required"
command -v wsl.exe >/dev/null 2>&1 || fail "wsl.exe is required"

REPO_ROOT_GITBASH="$(git rev-parse --show-toplevel 2>/dev/null)" || fail "run this script from inside the repository"
REPO_ROOT_WSL="$(gitbash_path_to_wsl "${REPO_ROOT_GITBASH}")"
BRIDGE_SCRIPT_WSL="${REPO_ROOT_WSL}/infra/scripts/publish-warehouse-image-wsl-bridge.sh"

exec env MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
    wsl.exe -d "${WSL_DISTRO}" -- bash "${BRIDGE_SCRIPT_WSL}" "${FORWARDED_ARGS[@]}"
