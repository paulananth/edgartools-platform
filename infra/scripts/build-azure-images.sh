#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  build-azure-images.sh --env <dev|prod> --acr-name <name> [--image-tag <tag>] [--role <pipelines|mdm-neo4j|all>]

Builds and pushes Azure runtime images outside Terraform. By default both
runtime images are built and tagged with the environment name plus an immutable
sha-<git-hash> tag.
USAGE
}

ENVIRONMENT=""
ACR_NAME=""
IMAGE_TAG=""
ROLE="all"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="${2:?}"; shift 2 ;;
    --acr-name) ACR_NAME="${2:?}"; shift 2 ;;
    --image-tag) IMAGE_TAG="${2:?}"; shift 2 ;;
    --role) ROLE="${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]]; then
  usage >&2
  exit 2
fi

if [[ -z "$ACR_NAME" ]]; then
  usage >&2
  exit 2
fi

IMAGE_TAG="${IMAGE_TAG:-$ENVIRONMENT}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "$ROLE" in
  pipelines|mdm-neo4j)
    bash "${SCRIPT_DIR}/publish-warehouse-image-acr.sh" \
      --acr-name "$ACR_NAME" \
      --image-role "$ROLE" \
      --image-tag "$IMAGE_TAG"
    ;;
  all)
    bash "${SCRIPT_DIR}/publish-warehouse-image-acr.sh" \
      --acr-name "$ACR_NAME" \
      --image-role pipelines \
      --image-tag "$IMAGE_TAG"
    bash "${SCRIPT_DIR}/publish-warehouse-image-acr.sh" \
      --acr-name "$ACR_NAME" \
      --image-role mdm-neo4j \
      --image-tag "$IMAGE_TAG"
    ;;
  *)
    echo "ERROR: --role must be pipelines, mdm-neo4j, or all" >&2
    exit 2
    ;;
esac
