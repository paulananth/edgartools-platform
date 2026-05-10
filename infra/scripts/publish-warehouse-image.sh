#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  publish-warehouse-image.sh --aws-region <region> --ecr-repository <name> [options]

Required:
  --aws-region <region>          AWS region for ECR.
  --ecr-repository <name>        ECR repository name, for example edgartools-dev-warehouse.

Optional:
  --role <role>                  warehouse, mdm, deps-warehouse, or deps-mdm. Default: warehouse.
  --image-tag <tag>              Image tag. Defaults to git SHA for final images and lock hash for deps images.
  --aws-profile <profile>        AWS CLI profile name.
  --context <path>               Docker build context. Default: repo root.
  --dockerfile <path>            Override Dockerfile path.
  --platform <platform>          Target platform. Default: linux/amd64.
  --mode <auto|docker|buildx>    Build mode. auto defaults to docker on macOS Colima and buildx on Linux/Windows.
                                  Aliases: macos-docker, linux-buildx, windows-buildx, linux.
  --deps-repository <name>       Dependency image ECR repository for final images.
  --deps-tag <tag>               Dependency image tag. Default: lock hash.
  --dependency-image <ref>       Explicit dependency image ref for final image build.
  --build-deps                   Build missing dependency image. Default.
  --skip-deps-build              Fail if dependency image is missing.
  --cache-from-tag <tag>         Plain Docker cache source tag, usually dev.
  --cache-tag <tag>              Buildx registry cache tag; plain Docker also tags this image for cache-from.
  --also-tag <tag>               Additional image tag to push. Repeatable.
  --push-attempts <count>        Retry buildx push this many times. Default: 1.
  --output-file <path>           Write final image reference with digest.
  --help                         Show this help.

Fast feedback defaults:
  macOS + Colima: --mode docker --cache-from-tag dev --also-tag dev
  Linux/Windows: --mode buildx --cache-tag buildcache --also-tag dev
EOF
}

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

log() {
    echo "==> $*" >&2
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

is_empty() {
    [[ -z "${1:-}" || "${1:-}" == "null" || "${1:-}" == "None" ]]
}

aws_cli() {
    if [[ -n "${AWS_PROFILE_NAME}" ]]; then
        aws --profile "${AWS_PROFILE_NAME}" --region "${AWS_REGION}" "$@"
    else
        aws --region "${AWS_REGION}" "$@"
    fi
}

host_os() {
    uname -s
}

linux_host() {
    [[ "$(host_os)" == Linux* ]]
}

macos_host() {
    [[ "$(host_os)" == Darwin* ]]
}

windows_host() {
    case "$(host_os)" in
        MINGW*|MSYS*|CYGWIN*) return 0 ;;
        *) return 1 ;;
    esac
}

linux_docker_daemon() {
    local docker_os
    command -v docker >/dev/null 2>&1 || return 1
    docker_os="$(docker info --format '{{.OSType}}' 2>/dev/null || true)"
    [[ "${docker_os}" == "linux" ]]
}

buildx_available() {
    command -v docker >/dev/null 2>&1 && docker buildx version >/dev/null 2>&1
}

repo_root() {
    cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

abs_path() {
    local path="$1"
    if [[ "${path}" == /* ]]; then
        printf '%s\n' "${path}"
    else
        (cd "${path}" && pwd)
    fi
}

append_csv_tags() {
    local input="$1" tag
    IFS=',' read -r -a _tags <<< "${input}"
    for tag in "${_tags[@]}"; do
        tag="${tag//[[:space:]]/}"
        [[ -n "${tag}" ]] && ALSO_TAGS+=("${tag}")
    done
}

dependency_hash_tag() {
    local deps_dockerfile="$1"
    python3 - "$REPO_ROOT" "$deps_dockerfile" <<'PY'
import hashlib
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
deps_dockerfile = pathlib.Path(sys.argv[2])
hasher = hashlib.sha256()
for path in [root / "pyproject.toml", root / "uv.lock", deps_dockerfile]:
    hasher.update(path.name.encode())
    hasher.update(b"\0")
    hasher.update(path.read_bytes())
    hasher.update(b"\0")
print("deps-" + hasher.hexdigest()[:16])
PY
}

git_image_tag() {
    git -C "${REPO_ROOT}" rev-parse --short=12 HEAD 2>/dev/null || printf 'local'
}

ensure_ecr_repository() {
    local repository="$1"
    if aws_cli ecr describe-repositories --repository-names "${repository}" >/dev/null 2>&1; then
        return 0
    fi
    log "Creating ECR repository ${repository}"
    aws_cli ecr create-repository \
        --repository-name "${repository}" \
        --image-scanning-configuration scanOnPush=true \
        --encryption-configuration encryptionType=AES256 >/dev/null
}

image_tag_exists() {
    local repository="$1" tag="$2"
    aws_cli ecr describe-images \
        --repository-name "${repository}" \
        --image-ids "imageTag=${tag}" >/dev/null 2>&1
}

verify_image_in_ecr() {
    local digest
    digest="$(
        aws_cli ecr describe-images \
            --repository-name "${ECR_REPOSITORY}" \
            --image-ids "imageTag=${IMAGE_TAG}" \
            --query 'imageDetails[0].imageDigest' \
            --output text
    )"
    if is_empty "${digest}"; then
        fail "image tag ${IMAGE_TAG} was not found in ECR repository ${ECR_REPOSITORY}"
    fi
    FINAL_IMAGE_REF="${REGISTRY}/${ECR_REPOSITORY}@${digest}"
    echo "${FINAL_IMAGE_REF}"
    if [[ -n "${OUTPUT_FILE}" ]]; then
        printf '%s\n' "${FINAL_IMAGE_REF}" > "${OUTPUT_FILE}"
    fi
}

normalize_mode() {
    case "$1" in
        auto) printf '%s\n' auto ;;
        docker|macos-docker) printf '%s\n' docker ;;
        buildx|linux|linux-buildx|windows-buildx) printf '%s\n' buildx ;;
        crane) printf '%s\n' crane ;;
        *) fail "--mode must be one of auto, docker, buildx, macos-docker, linux-buildx, windows-buildx" ;;
    esac
}

resolve_mode() {
    local normalized="$1"
    if [[ "${normalized}" != auto ]]; then
        printf '%s\n' "${normalized}"
        return 0
    fi
    if linux_host || windows_host; then
        printf '%s\n' buildx
    elif macos_host; then
        printf '%s\n' docker
    elif buildx_available; then
        printf '%s\n' buildx
    else
        printf '%s\n' docker
    fi
}

ensure_container_builder() {
    local builder_name
    builder_name="${BUILDX_BUILDER_NAME:-edgartools-publish-builder}"

    if ! docker buildx inspect "${builder_name}" >/dev/null 2>&1; then
        docker buildx create --name "${builder_name}" --driver docker-container --use >/dev/null
    else
        docker buildx use "${builder_name}" >/dev/null
    fi
    docker buildx inspect --bootstrap >/dev/null
}

docker_login() {
    aws_cli ecr get-login-password | docker login --username AWS --password-stdin "${REGISTRY}"
}

build_tag_args() {
    local tag
    TAG_ARGS=(--tag "${REMOTE_IMAGE_REF}")
    for tag in ${ALSO_TAGS[@]+"${ALSO_TAGS[@]}"}; do
        TAG_ARGS+=(--tag "${REGISTRY}/${ECR_REPOSITORY}:${tag}")
    done
}

build_arg_args() {
    BUILD_ARG_ARGS=()
    if [[ -n "${DEPENDENCY_IMAGE}" ]]; then
        BUILD_ARG_ARGS+=(--build-arg "DEPENDENCY_IMAGE=${DEPENDENCY_IMAGE}")
    fi
}

publish_docker() {
    local cache_ref tag
    require_command docker
    linux_docker_daemon || fail "docker mode requires a Linux Docker daemon such as macOS Colima"
    docker_login

    if [[ -n "${DEPENDENCY_IMAGE}" ]]; then
        docker pull "${DEPENDENCY_IMAGE}" >/dev/null || true
    fi
    if [[ -n "${CACHE_FROM_TAG}" ]]; then
        cache_ref="${REGISTRY}/${ECR_REPOSITORY}:${CACHE_FROM_TAG}"
        docker pull "${cache_ref}" >/dev/null || true
        DOCKER_CACHE_ARGS=(--cache-from "${cache_ref}")
    else
        DOCKER_CACHE_ARGS=()
    fi
    if [[ -n "${CACHE_TAG}" ]]; then
        TAG_ARGS+=(--tag "${REGISTRY}/${ECR_REPOSITORY}:${CACHE_TAG}")
    fi

    docker build \
        --platform "${PLATFORM}" \
        ${TAG_ARGS[@]+"${TAG_ARGS[@]}"} \
        ${BUILD_ARG_ARGS[@]+"${BUILD_ARG_ARGS[@]}"} \
        ${DOCKER_CACHE_ARGS[@]+"${DOCKER_CACHE_ARGS[@]}"} \
        --file "${DOCKERFILE_PATH}" \
        "${BUILD_CONTEXT}"

    docker push "${REMOTE_IMAGE_REF}"
    for tag in ${ALSO_TAGS[@]+"${ALSO_TAGS[@]}"}; do
        docker push "${REGISTRY}/${ECR_REPOSITORY}:${tag}"
    done
    if [[ -n "${CACHE_TAG}" ]]; then
        docker push "${REGISTRY}/${ECR_REPOSITORY}:${CACHE_TAG}"
    fi
}

publish_buildx() {
    local attempt sleep_seconds
    require_command docker
    buildx_available || fail "docker buildx is required for buildx mode"
    ensure_container_builder
    docker_login

    BUILDX_CACHE_ARGS=()
    if [[ -n "${CACHE_TAG}" ]]; then
        BUILDX_CACHE_ARGS+=(
            --cache-from "type=registry,ref=${REGISTRY}/${ECR_REPOSITORY}:${CACHE_TAG}"
            --cache-to "type=registry,ref=${REGISTRY}/${ECR_REPOSITORY}:${CACHE_TAG},mode=max"
        )
    fi

    attempt=1
    while true; do
        if docker buildx build \
            --platform "${PLATFORM}" \
            --provenance=false \
            --sbom=false \
            --push \
            ${TAG_ARGS[@]+"${TAG_ARGS[@]}"} \
            ${BUILD_ARG_ARGS[@]+"${BUILD_ARG_ARGS[@]}"} \
            ${BUILDX_CACHE_ARGS[@]+"${BUILDX_CACHE_ARGS[@]}"} \
            --file "${DOCKERFILE_PATH}" \
            "${BUILD_CONTEXT}"; then
            break
        fi
        if (( attempt >= PUSH_ATTEMPTS )); then
            fail "buildx publish failed after ${attempt} attempt(s)"
        fi
        sleep_seconds=$((attempt * 15))
        log "buildx publish attempt ${attempt}/${PUSH_ATTEMPTS} failed; retrying in ${sleep_seconds}s"
        attempt=$((attempt + 1))
        sleep "${sleep_seconds}"
    done
}

publish_crane() {
    local crane_bin tar_path local_image_ref
    require_command docker
    require_command aws
    crane_bin="${CRANE_BIN:-crane}"
    require_command "${crane_bin}"
    buildx_available || fail "docker buildx is required for crane mode"

    local_image_ref="${LOCAL_IMAGE_NAME:-edgartools-${ROLE}:${IMAGE_TAG}}"
    tar_path="${TARBALL_PATH:-/tmp/${ECR_REPOSITORY//\//-}-${IMAGE_TAG}-${PLATFORM//\//-}.tar}"

    docker buildx build \
        --platform "${PLATFORM}" \
        --provenance=false \
        --sbom=false \
        --load \
        --tag "${local_image_ref}" \
        ${BUILD_ARG_ARGS[@]+"${BUILD_ARG_ARGS[@]}"} \
        --file "${DOCKERFILE_PATH}" \
        "${BUILD_CONTEXT}"

    docker save --platform "${PLATFORM}" "${local_image_ref}" --output "${tar_path}"
    aws_cli ecr get-login-password | "${crane_bin}" auth login --username AWS --password-stdin "${REGISTRY}"
    "${crane_bin}" push "${tar_path}" "${REMOTE_IMAGE_REF}"
}

build_dependency_image_if_needed() {
    local deps_role deps_args=()
    case "${ROLE}" in
        warehouse) deps_role="deps-warehouse" ;;
        mdm) deps_role="deps-mdm" ;;
        *) return 0 ;;
    esac

    if [[ -n "${DEPENDENCY_IMAGE}" ]]; then
        return 0
    fi

    DEPS_REPOSITORY="${DEPS_REPOSITORY:-${ECR_REPOSITORY}-deps}"
    DEPS_DOCKERFILE="${DEPS_DOCKERFILE:-${REPO_ROOT}/Dockerfile.${deps_role#deps-}-deps}"
    DEPS_TAG="${DEPS_TAG:-$(dependency_hash_tag "${DEPS_DOCKERFILE}")}"
    DEPENDENCY_IMAGE="${REGISTRY}/${DEPS_REPOSITORY}:${DEPS_TAG}"

    ensure_ecr_repository "${DEPS_REPOSITORY}"
    if image_tag_exists "${DEPS_REPOSITORY}" "${DEPS_TAG}"; then
        log "Using dependency image ${DEPENDENCY_IMAGE}"
        return 0
    fi
    if [[ "${BUILD_DEPS}" == "false" ]]; then
        fail "dependency image ${DEPENDENCY_IMAGE} is missing; rerun without --skip-deps-build"
    fi

    log "Building missing dependency image ${DEPENDENCY_IMAGE}"
    deps_args=(
        --aws-region "${AWS_REGION}"
        --ecr-repository "${DEPS_REPOSITORY}"
        --role "${deps_role}"
        --image-tag "${DEPS_TAG}"
        --mode "${REQUESTED_MODE}"
        --platform "${PLATFORM}"
        --context "${BUILD_CONTEXT}"
        --push-attempts "${PUSH_ATTEMPTS}"
    )
    if [[ -n "${AWS_PROFILE_NAME}" ]]; then
        deps_args+=(--aws-profile "${AWS_PROFILE_NAME}")
    fi
    if [[ -n "${CACHE_TAG}" ]]; then
        deps_args+=(--cache-tag "${CACHE_TAG}")
    fi
    if [[ -n "${CACHE_FROM_TAG}" ]]; then
        deps_args+=(--cache-from-tag "${CACHE_FROM_TAG}")
    fi
    bash "${BASH_SOURCE[0]}" "${deps_args[@]}"
}

role_defaults() {
    case "${ROLE}" in
        warehouse)
            DOCKERFILE_PATH="${DOCKERFILE_PATH:-${REPO_ROOT}/Dockerfile}"
            ;;
        mdm)
            DOCKERFILE_PATH="${DOCKERFILE_PATH:-${REPO_ROOT}/Dockerfile.mdm-neo4j}"
            ;;
        deps-warehouse)
            DOCKERFILE_PATH="${DOCKERFILE_PATH:-${REPO_ROOT}/Dockerfile.warehouse-deps}"
            ;;
        deps-mdm)
            DOCKERFILE_PATH="${DOCKERFILE_PATH:-${REPO_ROOT}/Dockerfile.mdm-deps}"
            ;;
        *)
            fail "--role must be one of warehouse, mdm, deps-warehouse, deps-mdm"
            ;;
    esac
}

AWS_PROFILE_NAME=""
AWS_REGION=""
ECR_REPOSITORY=""
ROLE="warehouse"
IMAGE_TAG=""
BUILD_CONTEXT=""
DOCKERFILE_PATH=""
PLATFORM="linux/amd64"
REQUESTED_MODE="auto"
PUSH_ATTEMPTS=1
OUTPUT_FILE=""
LOCAL_IMAGE_NAME=""
DEPS_REPOSITORY=""
DEPS_TAG=""
DEPS_DOCKERFILE=""
DEPENDENCY_IMAGE=""
BUILD_DEPS="true"
CACHE_FROM_TAG=""
CACHE_TAG=""
ALSO_TAGS=()

REPO_ROOT="$(repo_root)"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --aws-profile) AWS_PROFILE_NAME="${2:?}"; shift 2 ;;
        --aws-region) AWS_REGION="${2:?}"; shift 2 ;;
        --ecr-repository) ECR_REPOSITORY="${2:?}"; shift 2 ;;
        --role) ROLE="${2:?}"; shift 2 ;;
        --image-tag) IMAGE_TAG="${2:?}"; shift 2 ;;
        --context) BUILD_CONTEXT="${2:?}"; shift 2 ;;
        --dockerfile) DOCKERFILE_PATH="${2:?}"; shift 2 ;;
        --platform) PLATFORM="${2:?}"; shift 2 ;;
        --mode) REQUESTED_MODE="${2:?}"; shift 2 ;;
        --push-attempts) PUSH_ATTEMPTS="${2:?}"; shift 2 ;;
        --output-file) OUTPUT_FILE="${2:?}"; shift 2 ;;
        --local-image) LOCAL_IMAGE_NAME="${2:?}"; shift 2 ;;
        --deps-repository) DEPS_REPOSITORY="${2:?}"; shift 2 ;;
        --deps-tag) DEPS_TAG="${2:?}"; shift 2 ;;
        --dependency-image) DEPENDENCY_IMAGE="${2:?}"; shift 2 ;;
        --build-deps) BUILD_DEPS="true"; shift ;;
        --skip-deps-build) BUILD_DEPS="false"; shift ;;
        --cache-from-tag) CACHE_FROM_TAG="${2:?}"; shift 2 ;;
        --cache-tag) CACHE_TAG="${2:?}"; shift 2 ;;
        --also-tag) append_csv_tags "${2:?}"; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) fail "unknown argument: $1" ;;
    esac
done

[[ -n "${AWS_REGION}" ]] || fail "--aws-region is required"
[[ -n "${ECR_REPOSITORY}" ]] || fail "--ecr-repository is required"
[[ "${PUSH_ATTEMPTS}" =~ ^[1-9][0-9]*$ ]] || fail "--push-attempts must be a positive integer"

require_command aws
require_command python3

BUILD_CONTEXT="$(abs_path "${BUILD_CONTEXT:-${REPO_ROOT}}")"
role_defaults
DOCKERFILE_PATH="$(abs_path "$(dirname "${DOCKERFILE_PATH}")")/$(basename "${DOCKERFILE_PATH}")"

NORMALIZED_MODE="$(normalize_mode "${REQUESTED_MODE}")"
RESOLVED_MODE="$(resolve_mode "${NORMALIZED_MODE}")"
if [[ "${RESOLVED_MODE}" == "buildx" ]] && ! buildx_available; then
    fail "buildx mode requires docker buildx; use --mode docker on macOS Colima if buildx is not installed"
fi

if [[ "${RESOLVED_MODE}" == "docker" ]] && ! linux_docker_daemon; then
    fail "docker mode requires a Linux Docker daemon such as macOS Colima or Docker Desktop"
fi

ACCOUNT_ID="$(aws_cli sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

if [[ -z "${IMAGE_TAG}" ]]; then
    case "${ROLE}" in
        deps-warehouse|deps-mdm) IMAGE_TAG="$(dependency_hash_tag "${DOCKERFILE_PATH}")" ;;
        *) IMAGE_TAG="$(git_image_tag)" ;;
    esac
fi

ensure_ecr_repository "${ECR_REPOSITORY}"
build_dependency_image_if_needed

REMOTE_IMAGE_REF="${REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"
build_tag_args
build_arg_args

log "Publishing ${ROLE} image ${REMOTE_IMAGE_REF} with ${RESOLVED_MODE} mode"
case "${RESOLVED_MODE}" in
    docker) publish_docker ;;
    buildx) publish_buildx ;;
    crane) publish_crane ;;
    *) fail "unsupported resolved mode: ${RESOLVED_MODE}" ;;
esac

verify_image_in_ecr
