#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  publish-warehouse-image.sh --aws-region <region> --ecr-repository <name> --image-tag <tag> [options]

Required:
  --aws-region <region>          AWS region for ECR
  --ecr-repository <name>        ECR repository name, for example edgartools-dev-warehouse
  --image-tag <tag>              Immutable image tag, usually a git SHA

Optional:
  --aws-profile <profile>        AWS CLI profile name
  --context <path>               Docker build context (default: .)
  --dockerfile <path>            Dockerfile path (default: Dockerfile)
  --platform <platform>          Target platform (default: linux/amd64)
  --local-image <name>           Local image name for fallback mode
  --mode <auto|linux|crane>      Publish mode (default: auto)
  --push-attempts <count>        Retry linux push this many times (default: 1)
  --output-file <path>           Write the final image reference with digest to a file
  --help                         Show this help

Modes:
  auto   Use linux mode on Linux hosts; otherwise use crane fallback mode.
  linux  Direct buildx push with provenance and SBOM enabled. Intended for CI, WSL, EC2, and CodeBuild.
  crane  Windows fallback: build locally, save a single-platform tarball, and push it with crane.
EOF
}

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

aws_cli() {
    if [[ -n "${AWS_PROFILE_NAME}" ]]; then
        aws --profile "${AWS_PROFILE_NAME}" --region "${AWS_REGION}" "$@"
    else
        aws --region "${AWS_REGION}" "$@"
    fi
}

linux_host() {
    case "$(uname -s)" in
        Linux*) return 0 ;;
        *) return 1 ;;
    esac
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

verify_image_in_ecr() {
    local digest
    digest="$(
        aws_cli ecr describe-images \
            --repository-name "${ECR_REPOSITORY}" \
            --image-ids "imageTag=${IMAGE_TAG}" \
            --query 'imageDetails[0].imageDigest' \
            --output text
    )"

    if [[ -z "${digest}" || "${digest}" == "None" ]]; then
        fail "image tag ${IMAGE_TAG} was not found in ECR repository ${ECR_REPOSITORY}"
    fi

    FINAL_IMAGE_REF="${REGISTRY}/${ECR_REPOSITORY}@${digest}"
    echo "${FINAL_IMAGE_REF}"

    if [[ -n "${OUTPUT_FILE}" ]]; then
        printf '%s\n' "${FINAL_IMAGE_REF}" > "${OUTPUT_FILE}"
    fi
}

publish_linux() {
    local attempt sleep_seconds

    require_command docker
    require_command aws

    docker buildx version >/dev/null 2>&1 || fail "docker buildx is required for linux publish mode"
    ensure_container_builder

    aws_cli ecr get-login-password \
        | docker login --username AWS --password-stdin "${REGISTRY}"

    attempt=1
    while true; do
        if docker buildx build \
            --platform "${PLATFORM}" \
            --provenance=true \
            --sbom=true \
            --push \
            --tag "${REMOTE_IMAGE_REF}" \
            --file "${DOCKERFILE_PATH}" \
            "${BUILD_CONTEXT}"; then
            break
        fi

        if (( attempt >= PUSH_ATTEMPTS )); then
            fail "linux publish failed after ${attempt} attempt(s)"
        fi

        sleep_seconds=$((attempt * 15))
        echo "linux publish attempt ${attempt}/${PUSH_ATTEMPTS} failed; retrying in ${sleep_seconds}s" >&2
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

    docker buildx version >/dev/null 2>&1 || fail "docker buildx is required for crane publish mode"

    local_image_ref="${LOCAL_IMAGE_NAME:-edgartools-warehouse:${IMAGE_TAG}}"
    tar_path="${TARBALL_PATH:-/tmp/${ECR_REPOSITORY//\//-}-${IMAGE_TAG}-${PLATFORM//\//-}.tar}"

    docker buildx build \
        --platform "${PLATFORM}" \
        --provenance=false \
        --sbom=false \
        --load \
        --tag "${local_image_ref}" \
        --file "${DOCKERFILE_PATH}" \
        "${BUILD_CONTEXT}"

    docker save \
        --platform "${PLATFORM}" \
        "${local_image_ref}" \
        --output "${tar_path}"

    aws_cli ecr get-login-password \
        | "${crane_bin}" auth login --username AWS --password-stdin "${REGISTRY}"

    "${crane_bin}" push "${tar_path}" "${REMOTE_IMAGE_REF}"
}

AWS_PROFILE_NAME=""
AWS_REGION=""
ECR_REPOSITORY=""
IMAGE_TAG=""
BUILD_CONTEXT="."
DOCKERFILE_PATH="Dockerfile"
PLATFORM="linux/amd64"
PUBLISH_MODE="auto"
PUSH_ATTEMPTS=1
OUTPUT_FILE=""
LOCAL_IMAGE_NAME=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --aws-profile)
            AWS_PROFILE_NAME="$2"
            shift 2
            ;;
        --aws-region)
            AWS_REGION="$2"
            shift 2
            ;;
        --ecr-repository)
            ECR_REPOSITORY="$2"
            shift 2
            ;;
        --image-tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        --context)
            BUILD_CONTEXT="$2"
            shift 2
            ;;
        --dockerfile)
            DOCKERFILE_PATH="$2"
            shift 2
            ;;
        --platform)
            PLATFORM="$2"
            shift 2
            ;;
        --mode)
            PUBLISH_MODE="$2"
            shift 2
            ;;
        --push-attempts)
            PUSH_ATTEMPTS="$2"
            shift 2
            ;;
        --output-file)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --local-image)
            LOCAL_IMAGE_NAME="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            fail "unknown argument: $1"
            ;;
    esac
done

[[ -n "${AWS_REGION}" ]] || fail "--aws-region is required"
[[ -n "${ECR_REPOSITORY}" ]] || fail "--ecr-repository is required"
[[ -n "${IMAGE_TAG}" ]] || fail "--image-tag is required"
[[ "${PUSH_ATTEMPTS}" =~ ^[1-9][0-9]*$ ]] || fail "--push-attempts must be a positive integer"

require_command aws

ACCOUNT_ID="$(aws_cli sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
REMOTE_IMAGE_REF="${REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}"

case "${PUBLISH_MODE}" in
    auto)
        if linux_host; then
            RESOLVED_MODE="linux"
        else
            RESOLVED_MODE="crane"
        fi
        ;;
    linux|crane)
        RESOLVED_MODE="${PUBLISH_MODE}"
        ;;
    *)
        fail "--mode must be one of auto, linux, crane"
        ;;
esac

if [[ "${RESOLVED_MODE}" == "linux" ]] && ! linux_host; then
    fail "linux mode requires a Linux runner (CI, CodeBuild, EC2, or WSL)"
fi

case "${RESOLVED_MODE}" in
    linux)
        publish_linux
        ;;
    crane)
        publish_crane
        ;;
esac

verify_image_in_ecr
