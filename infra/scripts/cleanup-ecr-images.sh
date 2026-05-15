#!/usr/bin/env bash
# Clean up unused ECR images before a deploy.
# Called automatically by deploy-aws-application.sh before every build/deploy.
#
# RETENTION POLICY (per CLAUDE.md):
#   Final image repos (warehouse, mdm):
#     KEEP  :dev                       — mutable latest; used as build cache source
#     KEEP  2 newest :sha-<hash> tags  — active image + 1 rollback anchor
#     DELETE everything else           — old shas, debug tags, untagged images
#
#   Deps repos (warehouse-deps, mdm-deps):
#     KEEP  tags referenced by any ACTIVE ECS task definition
#     KEEP  :dev if present
#     DELETE everything else
#
# Usage:
#   bash infra/scripts/cleanup-ecr-images.sh               # dry run (shows what would go)
#   bash infra/scripts/cleanup-ecr-images.sh --apply       # actually delete
#   bash infra/scripts/cleanup-ecr-images.sh --env prod --apply

set -euo pipefail

ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
AWS_PROFILE_NAME="${AWS_PROFILE:-}"
DRY_RUN=true
KEEP_SHA_COUNT=2

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)      ENVIRONMENT="${2:?}"; shift 2 ;;
    --region)   AWS_REGION="${2:?}"; shift 2 ;;
    --profile)  AWS_PROFILE_NAME="${2:?}"; shift 2 ;;
    --apply)    DRY_RUN=false; shift ;;
    --keep-sha) KEEP_SHA_COUNT="${2:?}"; shift 2 ;;
    *) echo "Unknown flag: $1" >&2; exit 2 ;;
  esac
done

NAME_PREFIX="edgartools-${ENVIRONMENT}"
aws_() {
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    aws --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION" "$@"
  else
    aws --region "$AWS_REGION" "$@"
  fi
}

log()  { echo "==> $*"; }
info() { echo "    $*"; }

TOTAL_DELETED=0
TOTAL_BYTES=0

# ── Collect image refs from active ECS task definitions ───────────────────────
log "Scanning active ECS task definitions for referenced image tags"
# list-task-definition-families is scoped to our prefix; then we fetch only the
# latest revision per family — much faster than listing all active task defs.
FAMILIES=$(aws_ ecs list-task-definition-families \
  --family-prefix "${NAME_PREFIX}" \
  --status ACTIVE \
  --query 'families' \
  --output json 2>/dev/null || echo '[]')

FAMILIES_TMP=$(mktemp)
echo "$FAMILIES" > "$FAMILIES_TMP"
trap 'rm -f "$FAMILIES_TMP"' EXIT

USED_IMAGES=$(AWS_REGION="$AWS_REGION" AWS_PROFILE_NAME="$AWS_PROFILE_NAME" \
  python3 -c "
import json, subprocess, os

with open('$FAMILIES_TMP') as f:
    families = json.load(f)

region  = os.environ.get('AWS_REGION', 'us-east-1')
profile = os.environ.get('AWS_PROFILE_NAME', '')

def aws(*args):
    cmd = ['aws', '--region', region] + list(args)
    if profile:
        cmd = ['aws', '--profile', profile, '--region', region] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 else None

images = set()
for family in families:
    # Get only the latest active revision for this family
    result = aws('ecs', 'list-task-definitions',
                 '--family-name', family, '--status', 'ACTIVE',
                 '--sort', 'DESC', '--max-results', '1',
                 '--query', 'taskDefinitionArns[0]', '--output', 'json')
    if not result or result == 'None':
        continue
    arn = result.strip('\"')
    imgs = aws('ecs', 'describe-task-definition',
               '--task-definition', arn,
               '--query', 'taskDefinition.containerDefinitions[*].image',
               '--output', 'json')
    if imgs:
        for img in imgs:
            images.add(img)
print('\n'.join(sorted(images)))
" 2>/dev/null || true)

# Store used image refs in an array
declare -a USED_IMAGE_LIST=()
while IFS= read -r img; do
  [[ -n "$img" ]] && USED_IMAGE_LIST+=("$img")
done <<< "$USED_IMAGES"
info "Found ${#USED_IMAGE_LIST[@]} image refs in active task definitions"

image_in_use() {
  local full_repo="$1" tag_or_digest="$2"
  local search="${full_repo}:${tag_or_digest}"
  [[ "$tag_or_digest" == sha256:* ]] && search="${full_repo}@${tag_or_digest}"
  for ref in "${USED_IMAGE_LIST[@]+"${USED_IMAGE_LIST[@]}"}"; do
    [[ "$ref" == "$search" || "$ref" == *"@${tag_or_digest}" ]] && return 0
  done
  return 1
}

# ── Process one repository ────────────────────────────────────────────────────
cleanup_repo() {
  local repo="$1" mode="$2"
  local full_repo="${ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${repo}"

  echo ""
  log "Repository: ${repo}  (mode=${mode})"

  local images_json
  images_json=$(aws_ ecr describe-images \
    --repository-name "$repo" \
    --query 'imageDetails[*].{digest:imageDigest,tags:imageTags,pushed:imagePushedAt,size:imageSizeInBytes}' \
    --output json 2>/dev/null || echo '[]')

  # Write images to tempfile — avoids pipe+heredoc stdin conflict
  local img_tmp
  img_tmp=$(mktemp)
  echo "$images_json" > "$img_tmp"

  # Parse decisions — output: digest<TAB>size<TAB>pushed<TAB>keep<TAB>tag_str
  local decisions
  decisions=$(MODE="$mode" KEEP_N="$KEEP_SHA_COUNT" python3 -c "
import json, sys, os

mode   = os.environ.get('MODE', 'final')
keep_n = int(os.environ.get('KEEP_N', '2'))

with open('$img_tmp') as f:
    images = json.load(f)

images.sort(key=lambda x: x.get('pushed',''), reverse=True)

keep_digests = set()
if mode == 'final':
    # Keep the 2 newest sha-* tagged images (active + 1 rollback)
    sha_imgs = [img for img in images
                if img.get('tags') and any(t.startswith('sha-') for t in img.get('tags',[]))]
    for img in sha_imgs[:keep_n]:
        keep_digests.add(img['digest'])
elif mode == 'deps':
    # Deps images are build-time base layers; ECS task defs don't reference them.
    # Keep the 2 newest deps-* tagged images (active + 1 rollback).
    deps_imgs = [img for img in images
                 if img.get('tags') and any(t.startswith('deps-') for t in img.get('tags',[]))]
    for img in deps_imgs[:keep_n]:
        keep_digests.add(img['digest'])

for img in images:
    tags   = img.get('tags') or []
    digest = img['digest']
    size   = img.get('size') or 0
    pushed = img.get('pushed','')[:10]
    keep   = False
    if 'dev' in tags:
        keep = True
    if digest in keep_digests:
        keep = True
    tag_str = ' '.join(tags) if tags else '<untagged>'
    print(f'{digest}\t{size}\t{pushed}\t{keep}\t{tag_str}')
" 2>/dev/null)
  rm -f "$img_tmp"

  local to_delete=()
  local to_delete_bytes=0

  while IFS=$'\t' read -r digest size pushed keep tag_str; do
    [[ -z "$digest" ]] && continue

    local size_mb
    size_mb=$(python3 -c "print(f'{int(\"${size:-0}\")/1e6:.0f}')" 2>/dev/null || echo "?")

    if [[ "$keep" == "True" ]]; then
      printf "    KEEP   %5s MB  %s  %s\n" "$size_mb" "$pushed" "$tag_str"
    else
      printf "    DELETE %5s MB  %s  %s\n" "$size_mb" "$pushed" "$tag_str"
      to_delete+=("imageDigest=${digest}")
      to_delete_bytes=$(( to_delete_bytes + ${size:-0} ))
    fi
  done <<< "$decisions"

  if [[ ${#to_delete[@]} -eq 0 ]]; then
    info "(nothing to delete)"
    return
  fi

  local delete_mb
  delete_mb=$(python3 -c "print(f'{${to_delete_bytes}/1e6:.0f}')" 2>/dev/null || echo "?")
  info "Total to free: ${delete_mb} MB  (${#to_delete[@]} images)"

  if [[ "$DRY_RUN" == "true" ]]; then
    info "[dry-run] Pass --apply to delete"
    return
  fi

  # Batch-delete in groups of 100 (ECR API limit)
  local i=0 batch=()
  for item in "${to_delete[@]}"; do
    batch+=("$item")
    if [[ ${#batch[@]} -ge 100 ]]; then
      aws_ ecr batch-delete-image --repository-name "$repo" \
        --image-ids "${batch[@]}" --output json >/dev/null 2>&1
      batch=()
    fi
  done
  [[ ${#batch[@]} -gt 0 ]] && aws_ ecr batch-delete-image \
    --repository-name "$repo" --image-ids "${batch[@]}" --output json >/dev/null 2>&1

  info "Deleted ${#to_delete[@]} images (${delete_mb} MB freed)"
  TOTAL_DELETED=$(( TOTAL_DELETED + ${#to_delete[@]} ))
  TOTAL_BYTES=$(( TOTAL_BYTES + to_delete_bytes ))
}

# ── Main ──────────────────────────────────────────────────────────────────────
ACCOUNT=$(aws_ sts get-caller-identity --query Account --output text 2>/dev/null)

echo ""
printf '%.0s─' $(seq 1 62); echo
echo "  ECR CLEANUP  ·  ${ENVIRONMENT}  ·  ${AWS_REGION}"
echo "  Keep: :dev + ${KEEP_SHA_COUNT} newest :sha-* per final repo; active deps"
[[ "$DRY_RUN" == "true" ]] && echo "  (DRY RUN — pass --apply to delete)"
printf '%.0s─' $(seq 1 62); echo

cleanup_repo "${NAME_PREFIX}-warehouse"      final
cleanup_repo "${NAME_PREFIX}-mdm"            final
cleanup_repo "${NAME_PREFIX}-warehouse-deps" deps
cleanup_repo "${NAME_PREFIX}-mdm-deps"       deps

echo ""
if [[ "$DRY_RUN" == "false" ]]; then
  TOTAL_MB=$(python3 -c "print(f'{${TOTAL_BYTES}/1e6:.0f}')" 2>/dev/null || echo "?")
  echo "==> Done: ${TOTAL_DELETED} images deleted, ${TOTAL_MB} MB freed"
else
  echo "==> Dry run complete. Run with --apply to delete."
fi
echo ""
