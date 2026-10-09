#!/usr/bin/env bash
# Pull postgres:16-alpine for CI fixtures. One mirror often returns
# toomanyrequests on a shared runner address, so try the next mirror.
set -euo pipefail

images=(
  public.ecr.aws/docker/library/postgres:16-alpine
  mirror.gcr.io/library/postgres:16-alpine
)
for attempt in 1 2 3; do
  for image in "${images[@]}"; do
    if docker pull "$image"; then
      docker tag "$image" postgres:16-alpine
      exit 0
    fi
    echo "pull failed for ${image} on attempt ${attempt}" >&2
  done
  sleep $((attempt * 10))
done
echo "could not pull postgres:16-alpine from any mirror" >&2
exit 1
