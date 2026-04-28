#!/usr/bin/env bash
# Build and push one of the two edgar-warehouse images to Azure Container Registry.
#
# Images:
#   edgar-warehouse-pipelines  — warehouse ETL (S3/Azure Blob), built from Dockerfile.pipelines
#   edgar-warehouse-mdm-neo4j  — MDM pipeline + API (Azure SQL, Neo4j), built from Dockerfile.mdm-neo4j
#
# Every push writes two tags:
#   :<image-tag>      mutable environment tag (default: dev)
#   :sha-<git-hash>   immutable audit tag for rollback
#
# Usage:
#   publish-warehouse-image-acr.sh --acr-name edgdev7659acr --image-role pipelines
#   publish-warehouse-image-acr.sh --acr-name edgdev7659acr --image-role mdm-neo4j
#   publish-warehouse-image-acr.sh --acr-name edgdev7659acr --image-role mdm-neo4j --image-tag prod
#
# Rollback:
#   docker pull <acr>/edgar-warehouse-mdm-neo4j:sha-abc1234
#   docker tag  <acr>/edgar-warehouse-mdm-neo4j:sha-abc1234 <acr>/edgar-warehouse-mdm-neo4j:dev
#   docker push <acr>/edgar-warehouse-mdm-neo4j:dev

set -euo pipefail

usage() {
  grep '^#' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

ACR_NAME=""
IMAGE_ROLE=""
IMAGE_TAG="dev"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --acr-name)   ACR_NAME="${2:?}";   shift 2 ;;
    --image-role) IMAGE_ROLE="${2:?}"; shift 2 ;;
    --image-tag)  IMAGE_TAG="${2:?}";  shift 2 ;;
    -h|--help) usage ;;
    *) echo "Unknown argument: $1" >&2; usage ;;
  esac
done

if [[ -z "$ACR_NAME" || -z "$IMAGE_ROLE" ]]; then
  echo "ERROR: --acr-name and --image-role are required" >&2
  usage
fi

case "$IMAGE_ROLE" in
  pipelines)
    IMAGE_NAME="edgar-warehouse-pipelines"
    DOCKERFILE="Dockerfile.pipelines"
    ;;
  mdm-neo4j)
    IMAGE_NAME="edgar-warehouse-mdm-neo4j"
    DOCKERFILE="Dockerfile.mdm-neo4j"
    ;;
  *)
    echo "ERROR: --image-role must be 'pipelines' or 'mdm-neo4j', got: $IMAGE_ROLE" >&2
    exit 2
    ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SHA_TAG="sha-$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
LOGIN_SERVER="$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)"

IMAGE_REF="${LOGIN_SERVER}/${IMAGE_NAME}:${IMAGE_TAG}"
SHA_REF="${LOGIN_SERVER}/${IMAGE_NAME}:${SHA_TAG}"

echo "==> Image role : $IMAGE_ROLE"
echo "    Dockerfile : $DOCKERFILE"
echo "    Env tag    : $IMAGE_REF"
echo "    SHA tag    : $SHA_REF"

az acr login --name "$ACR_NAME"

docker build --platform linux/amd64 \
  -f "${REPO_ROOT}/${DOCKERFILE}" \
  -t "$IMAGE_REF" \
  -t "$SHA_REF" \
  "$REPO_ROOT"

docker push "$IMAGE_REF"
docker push "$SHA_REF"

echo ""
echo "Pushed:"
echo "  $IMAGE_REF"
echo "  $SHA_REF"
