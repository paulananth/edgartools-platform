#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  publish-warehouse-image.sh --aws-region <region> --ecr-repository <name> [options]

Required:
  --aws-region <region>          AWS region for ECR.
  --ecr-repository <name>        ECR repository name, for example edgartools-dev-images. One
                                  shared repository holds warehouse, mdm, and their deps images --
                                  role is encoded in the tag, not the repository name (see --role).

Optional:
  --role <role>                  warehouse, mdm, deps-warehouse, or deps-mdm. Default: warehouse.
                                  Also determines the tag prefix (warehouse-*/mdm-*) applied to
                                  --image-tag, --also-tag, --cache-tag, and --cache-from-tag values
                                  so the two roles never collide on a tag within the shared repo.
  --image-tag <tag>              Image tag (before role-prefixing). Defaults to git SHA for final
                                  images and lock hash for deps images.
  --aws-profile <profile>        AWS CLI profile name.
  --context <path>               Docker build context. Default: repo root.
  --dockerfile <path>            Override Dockerfile path.
  --platform <platform>          Target platform. Default: linux/amd64.
  --mode <docker|crane>          Build mode. Default: docker. auto and linux select docker.
  --deps-repository <name>       Dependency image ECR repository for final images. Default: same
                                  as --ecr-repository (deps images share the repo too).
  --deps-tag <tag>               Dependency image tag (before role-prefixing). Default: lock hash.
  --dependency-image <ref>       Explicit dependency image ref for final image build.
  --build-deps                   Build missing dependency image. Default.
  --skip-deps-build              Fail if dependency image is missing.
  --cache-from-tag <tag>         Plain Docker cache source tag, usually dev.
  --cache-tag <tag>              Extra tag to push, for a later --cache-from-tag.
  --also-tag <tag>               Additional image tag to push. Repeatable.
  --push-attempts <count>        Retry each docker push this many times. Default: 1.
  --output-file <path>           Write final image reference with digest.
  --help                         Show this help.

Publish with docker build and docker push on the configured Docker context,
including Linux and WSL:
  --mode docker --cache-from-tag dev --also-tag dev
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

linux_docker_daemon() {
    local docker_os
    command -v docker >/dev/null 2>&1 || return 1
    # WSL's Windows docker.exe keeps a trailing carriage return.
    docker_os="$(docker info --format '{{.OSType}}' 2>/dev/null | tr -d '\r' || true)"
    [[ "${docker_os}" == "linux" ]]
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
# The deps images build the source engine's wheel from crates/source-contract
# (mastering to-do 15), so a change there is a new deps image too.
engine = root / "crates" / "source-contract"
engine_files = sorted(
    p for p in engine.rglob("*")
    if p.is_file() and "target" not in p.relative_to(engine).parts
    and not p.relative_to(engine).parts[0] == "tests"
)
named = [(p.name, p) for p in (root / "pyproject.toml", root / "uv.lock", deps_dockerfile)]
named += [(p.relative_to(root).as_posix(), p) for p in engine_files]
for name, path in named:
    hasher.update(name.encode())
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
        auto|docker|macos-docker|linux) printf '%s\n' docker ;;
        crane) printf '%s\n' crane ;;
        *) fail "--mode must be docker or crane" ;;
    esac
}

docker_login() {
    # If a docker credential helper (e.g. docker-credential-ecr-login) is
    # configured for this registry, push/pull already authenticate per-request
    # via that helper. `docker login` then has nothing useful to persist and
    # fails with "error storing credentials ... not implemented" — harmless,
    # but fatal under `set -e`. Skip the redundant login in that case.
    if python3 -c "
import json, os, sys
path = os.path.expanduser('~/.docker/config.json')
try:
    with open(path) as f:
        cfg = json.load(f)
except (OSError, ValueError):
    sys.exit(1)
sys.exit(0 if '${REGISTRY}' in cfg.get('credHelpers', {}) else 1)
"; then
        log "Docker credential helper configured for ${REGISTRY}; skipping docker login"
        return 0
    fi
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

cleanup_local_images() {
    # Prune dangling layers and stale SHA tags for this repo before building.
    # Remove the dependency image so the next build pulls it again.
    local repo="${REGISTRY}/${ECR_REPOSITORY}"
    log "Cleaning local images for ${ECR_REPOSITORY}"
    docker image prune -f >/dev/null 2>&1 || true
    docker builder prune -af >/dev/null 2>&1 || true

    # Remove the deps base image so it gets freshly pulled (prevents stale layer corruption)
    if [[ -n "${DEPENDENCY_IMAGE}" ]]; then
        log "Removing cached deps image ${DEPENDENCY_IMAGE##*/} (will re-pull fresh)"
        docker rmi "${DEPENDENCY_IMAGE}" >/dev/null 2>&1 || true
    fi

    # Remove old <role>-sha-* tags for this role (keep only the newest one).
    # Tags are role-prefixed (warehouse-sha-*, mdm-sha-*) since the shared
    # repo holds both roles, so scope the prune to the current ROLE_PREFIX.
    local sha_tags old_tags
    sha_tags=$(docker images --format "{{.Tag}}" "${repo}" 2>/dev/null \
        | grep "^${ROLE_PREFIX}-sha-" | sort -r || true)
    old_tags=$(echo "$sha_tags" | tail -n +2 || true)
    while IFS= read -r tag; do
        [[ -z "$tag" ]] && continue
        log "Removing stale local image ${ECR_REPOSITORY}:${tag}"
        docker rmi "${repo}:${tag}" >/dev/null 2>&1 || true
    done <<< "$old_tags"
}

push_with_retries() {
    local ref="$1" attempt=1 sleep_seconds
    while true; do
        if docker push "${ref}"; then
            return 0
        fi
        if (( attempt >= PUSH_ATTEMPTS )); then
            fail "docker push failed for ${ref} after ${attempt} attempt(s)"
        fi
        sleep_seconds=$((attempt * 15))
        log "docker push attempt ${attempt}/${PUSH_ATTEMPTS} failed for ${ref}; retrying in ${sleep_seconds}s"
        attempt=$((attempt + 1))
        sleep "${sleep_seconds}"
    done
}

publish_docker() {
    local cache_ref tag
    require_command docker
    cleanup_local_images
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

    push_with_retries "${REMOTE_IMAGE_REF}"
    for tag in ${ALSO_TAGS[@]+"${ALSO_TAGS[@]}"}; do
        push_with_retries "${REGISTRY}/${ECR_REPOSITORY}:${tag}"
    done
    if [[ -n "${CACHE_TAG}" ]]; then
        push_with_retries "${REGISTRY}/${ECR_REPOSITORY}:${CACHE_TAG}"
    fi
}

publish_crane() {
    local crane_bin tar_path local_image_ref
    require_command docker
    require_command aws
    crane_bin="${CRANE_BIN:-crane}"
    require_command "${crane_bin}"

    local_image_ref="${LOCAL_IMAGE_NAME:-edgartools-${ROLE}:${IMAGE_TAG}}"
    tar_path="${TARBALL_PATH:-/tmp/${ECR_REPOSITORY//\//-}-${IMAGE_TAG}-${PLATFORM//\//-}.tar}"

    docker build \
        --platform "${PLATFORM}" \
        --tag "${local_image_ref}" \
        ${BUILD_ARG_ARGS[@]+"${BUILD_ARG_ARGS[@]}"} \
        --file "${DOCKERFILE_PATH}" \
        "${BUILD_CONTEXT}"

    docker save "${local_image_ref}" --output "${tar_path}"
    aws_cli ecr get-login-password | "${crane_bin}" auth login --username AWS --password-stdin "${REGISTRY}"
    "${crane_bin}" push "${tar_path}" "${REMOTE_IMAGE_REF}"
}

build_dependency_image_if_needed() {
    local deps_role deps_args=() deps_tag_input
    case "${ROLE}" in
        warehouse) deps_role="deps-warehouse" ;;
        mdm) deps_role="deps-mdm" ;;
        *) return 0 ;;
    esac

    if [[ -n "${DEPENDENCY_IMAGE}" ]]; then
        return 0
    fi

    # Deps images live in the same shared repo as the final image now; the
    # role prefix on the tag (applied below and, for the recursive build, by
    # the child invocation's own role_defaults) is what keeps warehouse and
    # mdm deps images from colliding.
    DEPS_REPOSITORY="${DEPS_REPOSITORY:-${ECR_REPOSITORY}}"
    DEPS_DOCKERFILE="${DEPS_DOCKERFILE:-${REPO_ROOT}/Dockerfile.${deps_role#deps-}-deps}"
    deps_tag_input="${DEPS_TAG:-$(dependency_hash_tag "${DEPS_DOCKERFILE}")}"
    DEPS_TAG="${ROLE_PREFIX}-${deps_tag_input}"
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
        --image-tag "${deps_tag_input}"
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
            ROLE_PREFIX="warehouse"
            ;;
        mdm)
            DOCKERFILE_PATH="${DOCKERFILE_PATH:-${REPO_ROOT}/Dockerfile.mdm-neo4j}"
            ROLE_PREFIX="mdm"
            ;;
        deps-warehouse)
            DOCKERFILE_PATH="${DOCKERFILE_PATH:-${REPO_ROOT}/Dockerfile.warehouse-deps}"
            ROLE_PREFIX="warehouse"
            ;;
        deps-mdm)
            DOCKERFILE_PATH="${DOCKERFILE_PATH:-${REPO_ROOT}/Dockerfile.mdm-deps}"
            ROLE_PREFIX="mdm"
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
ROLE_PREFIX=""
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

RESOLVED_MODE="$(normalize_mode "${REQUESTED_MODE}")"
if ! linux_docker_daemon; then
    fail "publishing requires a Linux Docker daemon (docker info reports OSType linux)"
fi

ACCOUNT_ID="$(aws_cli sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

if [[ -z "${IMAGE_TAG}" ]]; then
    case "${ROLE}" in
        deps-warehouse|deps-mdm) IMAGE_TAG="$(dependency_hash_tag "${DOCKERFILE_PATH}")" ;;
        *) IMAGE_TAG="$(git_image_tag)" ;;
    esac
fi

# Role-prefix every tag pushed to the shared repo (warehouse-*, mdm-*) so
# warehouse and mdm images never collide on tag names within one repository.
# Applies uniformly whether IMAGE_TAG came from a default above or an
# explicit --image-tag.
IMAGE_TAG="${ROLE_PREFIX}-${IMAGE_TAG}"
for _tag_index in "${!ALSO_TAGS[@]}"; do
    ALSO_TAGS[_tag_index]="${ROLE_PREFIX}-${ALSO_TAGS[_tag_index]}"
done
[[ -n "${CACHE_TAG}" ]] && CACHE_TAG="${ROLE_PREFIX}-${CACHE_TAG}"
[[ -n "${CACHE_FROM_TAG}" ]] && CACHE_FROM_TAG="${ROLE_PREFIX}-${CACHE_FROM_TAG}"

ensure_ecr_repository "${ECR_REPOSITORY}"
build_dependency_image_if_needed

REMOTE_IMAGE_REF="${REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"
build_tag_args
build_arg_args

log "Publishing ${ROLE} image ${REMOTE_IMAGE_REF} with ${RESOLVED_MODE} mode"
case "${RESOLVED_MODE}" in
    docker) publish_docker ;;
    crane) publish_crane ;;
    *) fail "unsupported resolved mode: ${RESOLVED_MODE}" ;;
esac

verify_image_in_ecr
