#!/usr/bin/env bash

set -euo pipefail

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

require_file() {
    [[ -f "$1" ]] || fail "missing required file: $1"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WINDOWS_DOCKER_BRIDGE="${WINDOWS_DOCKER_BRIDGE:-/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe}"
WINDOWS_AWS_BRIDGE="${WINDOWS_AWS_BRIDGE:-/mnt/c/Program Files/Amazon/AWSCLIV2/aws.exe}"
PUBLISH_HELPER="${REPO_ROOT}/infra/scripts/publish-warehouse-image.sh"
TMP_DIR="${REPO_ROOT}/.tmp"
LF_HELPER="${TMP_DIR}/publish-warehouse-image.lf.sh"
PUSH_ATTEMPTS_VALUE="${PUBLISH_ATTEMPTS:-3}"
FORWARDED_ARGS=()
MODE_SEEN=0

require_file "${WINDOWS_DOCKER_BRIDGE}"
require_file "${WINDOWS_AWS_BRIDGE}"
require_file "${PUBLISH_HELPER}"
mkdir -p "${TMP_DIR}"

docker() {
    "${WINDOWS_DOCKER_BRIDGE}" "$@"
}

aws() {
    "${WINDOWS_AWS_BRIDGE}" "$@" | tr -d '\r'
}

export -f docker
export -f aws
export WINDOWS_DOCKER_BRIDGE
export WINDOWS_AWS_BRIDGE

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)
            [[ $# -ge 2 ]] || fail "--mode requires a value"
            [[ "$2" == "linux" ]] || fail "publish-warehouse-image-wsl-bridge.sh only supports --mode linux"
            MODE_SEEN=1
            FORWARDED_ARGS+=("$1" "$2")
            shift 2
            ;;
        *)
            FORWARDED_ARGS+=("$1")
            shift
            ;;
    esac
done

if [[ "${MODE_SEEN}" -eq 0 ]]; then
    FORWARDED_ARGS+=(--mode linux)
fi

if ! printf '%s\n' "${FORWARDED_ARGS[@]}" | grep -q '^--push-attempts$'; then
    FORWARDED_ARGS+=(--push-attempts "${PUSH_ATTEMPTS_VALUE}")
fi

tr -d '\r' < "${PUBLISH_HELPER}" > "${LF_HELPER}"
chmod +x "${LF_HELPER}"

cd "${REPO_ROOT}"
exec bash "${LF_HELPER}" "${FORWARDED_ARGS[@]}"
