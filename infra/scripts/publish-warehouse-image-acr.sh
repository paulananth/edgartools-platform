#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  publish-warehouse-image-acr.sh --acr-name <name> --image-name <name> --image-tag <tag>

Builds the warehouse Docker image, logs into Azure Container Registry, pushes the
image, and prints the pushed image reference.
USAGE
}

ACR_NAME=""
IMAGE_NAME="edgar-warehouse"
IMAGE_TAG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --acr-name) ACR_NAME="${2:?}"; shift 2 ;;
    --image-name) IMAGE_NAME="${2:?}"; shift 2 ;;
    --image-tag) IMAGE_TAG="${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$ACR_NAME" || -z "$IMAGE_TAG" ]]; then
  usage >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOGIN_SERVER="$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)"
IMAGE_REF="${LOGIN_SERVER}/${IMAGE_NAME}:${IMAGE_TAG}"

az acr login --name "$ACR_NAME"
docker build --platform linux/amd64 -t "$IMAGE_REF" "$REPO_ROOT"
docker push "$IMAGE_REF"

echo "$IMAGE_REF"
