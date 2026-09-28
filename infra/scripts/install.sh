#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  install.sh [wizard|doctor|init|plan|deploy|report] [options]

Commands:
  wizard   Interactive TUI wizard. This is the default when no command is provided.
  doctor   Run read-only local, AWS CLI, SnowCLI, Terraform, Docker, and config checks.
  init     Create only ignored local wizard state/templates under .edgartools-install/.
  plan     Print the ordered install plan and exact commands as preview-only.
  deploy   Preview the plan. Use --apply to enable per-stage confirmation and execution.
  report   Write and print a sanitized install report.

Options:
  --env-name <slug>               Environment slug (e.g. prod, eu-prod). Required.
  --aws-profile <profile>         AWS admin/provisioning profile. Default: AWS_PROFILE or aws-admin-<env>.
  --aws-account-id <id>           Expected 12-digit AWS account ID. Required (or INSTALL_AWS_ACCOUNT_ID).
  --deployer-profile <profile>    AWS application deployer profile. Default: sec_platform_deployer.
  --aws-region <region>           AWS region. Default: AWS_REGION, AWS_DEFAULT_REGION, or us-east-1.
  --snow-connection <name>        SnowCLI connection name from ~/.snowflake/config.toml. Required (never derived from --env-name).
  --workspace <path>              Local ignored wizard workspace. Default: .edgartools-install.
  --report-file <path>            Report path for the report command.
  --apply                         deploy only: enable real commands, each behind a yes/no prompt.
  -h, --help                      Show this help.
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

ENVIRONMENT=""
AWS_PROFILE_NAME="${AWS_PROFILE:-}"
DEPLOYER_PROFILE="${INSTALL_DEPLOYER_PROFILE:-sec_platform_deployer}"
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
SNOW_CONNECTION=""
WORKSPACE=""
REPORT_FILE=""
APPLY=false
EXPECTED_AWS_ACCOUNT_ID="${INSTALL_AWS_ACCOUNT_ID:-}"
CANONICAL_PROD_DATABASE="EDGARTOOLS_PROD"

COMMAND="wizard"
if [[ $# -gt 0 ]]; then
  case "$1" in
    wizard|doctor|init|plan|deploy|report)
      COMMAND="$1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      COMMAND="wizard"
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-name) ENVIRONMENT="${2:?}"; shift 2 ;;
    --aws-profile) AWS_PROFILE_NAME="${2:?}"; shift 2 ;;
    --aws-account-id) EXPECTED_AWS_ACCOUNT_ID="${2:?}"; shift 2 ;;
    --deployer-profile) DEPLOYER_PROFILE="${2:?}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?}"; shift 2 ;;
    --snow-connection) SNOW_CONNECTION="${2:?}"; shift 2 ;;
    --workspace) WORKSPACE="${2:?}"; shift 2 ;;
    --report-file) REPORT_FILE="${2:?}"; shift 2 ;;
    --apply) APPLY=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "Unknown argument: $1" ;;
  esac
done

# The wizard prompts interactively for the environment and connection, so it is
# the one command allowed to start without them; every other command must be
# given both explicitly. --snow-connection is never derived from --env-name:
# deriving it is what let install.sh and deploy-snowflake-stack.sh disagree about
# the default connection for the same environment (CLAUDE.md, "SnowCLI connection
# naming").
# Environment identifier is a free-form operator-chosen slug (wayfinder ticket
# 01), not a closed dev|prod enum. Defined as a function because the wizard
# collects the slug interactively, after this point, and must validate it too --
# otherwise an empty or malformed answer flows into RESOURCE_PREFIX and
# SNOWFLAKE_DATABASE as "edgartools-" / "EDGARTOOLS_".
validate_env_slug() {
  case "$1" in
    "") fail "--env-name is required" ;;
    *--*) fail "--env-name '$1' is not a valid environment slug: hyphen-separated words must be non-empty" ;;
    *[!a-z0-9-]*|-*|*-|[!a-z]*) fail "--env-name '$1' is not a valid environment slug: use lowercase letters and digits in hyphen-separated words, starting with a letter (e.g. 'prod', 'eu-prod')" ;;
  esac
}

# The wizard prompts for both, so it alone may start without them; it validates
# the answers via validate_env_slug/the check below once collected.
if [[ "$COMMAND" != "wizard" ]]; then
  validate_env_slug "$ENVIRONMENT"
  # Never derived from --env-name: deriving it is what let install.sh and
  # deploy-snowflake-stack.sh disagree about the default connection for the same
  # environment (CLAUDE.md, "SnowCLI connection naming").
  [[ -n "$SNOW_CONNECTION" ]] || fail "--snow-connection is required (no default is derived from --env-name)"
elif [[ -n "$ENVIRONMENT" ]]; then
  validate_env_slug "$ENVIRONMENT"
fi

if [[ "$APPLY" == "true" && "$COMMAND" != "deploy" && "$COMMAND" != "wizard" ]]; then
  fail "--apply is only valid with deploy or wizard"
fi

EVENTS_FILE="${TMPDIR:-/tmp}/install-events-$$.tsv"
trap 'rm -f "${EVENTS_FILE}"' EXIT

refresh_config() {
  if [[ -z "$AWS_PROFILE_NAME" ]]; then
    AWS_PROFILE_NAME="aws-admin-${ENVIRONMENT}"
  fi
  WORKSPACE="${WORKSPACE:-${REPO_ROOT}/.edgartools-install}"
  STATE_FILE="${WORKSPACE}/state.json"
  # Hyphens are legal in a slug and in AWS resource names, but NOT in an
  # unquoted Snowflake identifier -- so the Snowflake side maps them to
  # underscores ("eu-prod" -> EDGARTOOLS_EU_PROD) while RESOURCE_PREFIX keeps
  # the hyphen. Same mapping as generate-snowflake-env.py's snowflake_segment();
  # for a slug with no hyphens (e.g. "prod") this is a no-op.
  ENV_UPPER="$(printf '%s' "$ENVIRONMENT" | tr '[:lower:]-' '[:upper:]_')"
  RESOURCE_PREFIX="edgartools-${ENVIRONMENT}"
  SNOWFLAKE_DATABASE="EDGARTOOLS_${ENV_UPPER}"
}

selected_aws_account_id() {
  aws --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION_NAME" sts get-caller-identity --query Account --output text
}

require_expected_aws_target() {
  local account_id
  account_id="$(selected_aws_account_id 2>/dev/null)" || fail "unable to resolve AWS account for profile ${AWS_PROFILE_NAME}"
  [[ "$account_id" == "$EXPECTED_AWS_ACCOUNT_ID" ]] || fail "AWS account mismatch: expected ${EXPECTED_AWS_ACCOUNT_ID}, got ${account_id}"
  if [[ "$ENVIRONMENT" == "prod" ]]; then
    [[ "$AWS_REGION_NAME" == "us-east-1" ]] || fail "prod must target us-east-1"
    [[ "$SNOWFLAKE_DATABASE" == "$CANONICAL_PROD_DATABASE" ]] || fail "production Snowflake target must be ${CANONICAL_PROD_DATABASE}"
  fi
}

use_gum() {
  [[ "${INSTALL_NO_GUM:-}" == "1" ]] && return 1
  command -v gum >/dev/null 2>&1 || return 1
  [[ "${INSTALL_FORCE_GUM:-}" == "1" ]] && return 0
  [[ -t 0 && -t 1 ]]
}

offer_gum_install() {
  [[ "${INSTALL_NO_GUM:-}" == "1" ]] && return 0
  command -v gum >/dev/null 2>&1 && return 0

  echo "gum is not installed. gum enables the richer terminal UI for this wizard."
  if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew was not found, so the wizard will continue with the plain Bash fallback."
    return 0
  fi
  if confirm "Install gum now with Homebrew?"; then
    brew install gum
    hash -r
    if command -v gum >/dev/null 2>&1; then
      echo "gum installed; continuing with the gum TUI."
    else
      echo "gum installation did not put gum on PATH; continuing with the plain Bash fallback."
    fi
  else
    echo "Continuing with the plain Bash fallback."
  fi
}

confirm() {
  local prompt="$1"
  local reply
  if use_gum; then
    gum confirm "$prompt"
    return $?
  fi
  printf '%s [y/N] ' "$prompt" >&2
  IFS= read -r reply || return 1
  case "$reply" in
    y|Y|yes|YES|Yes) return 0 ;;
    *) return 1 ;;
  esac
}

choose_one() {
  local prompt="$1" default_choice="$2" choice reply index
  shift 2
  local options=("$@")

  if use_gum; then
    choice="$(printf '%s\n' "${options[@]}" | gum choose --header "$prompt" --selected "$default_choice")" || return 1
    printf '%s\n' "$choice"
    return 0
  fi

  echo "$prompt" >&2
  for index in "${!options[@]}"; do
    if [[ "${options[$index]}" == "$default_choice" ]]; then
      printf '  %d) %s [default]\n' "$((index + 1))" "${options[$index]}" >&2
    else
      printf '  %d) %s\n' "$((index + 1))" "${options[$index]}" >&2
    fi
  done
  printf 'Select [%s]: ' "$default_choice" >&2
  IFS= read -r reply || return 1
  if [[ -z "$reply" ]]; then
    printf '%s\n' "$default_choice"
    return 0
  fi
  if [[ "$reply" =~ ^[0-9]+$ ]]; then
    index=$((reply - 1))
    if (( index >= 0 && index < ${#options[@]} )); then
      printf '%s\n' "${options[$index]}"
      return 0
    fi
  fi
  for choice in "${options[@]}"; do
    if [[ "$reply" == "$choice" ]]; then
      printf '%s\n' "$choice"
      return 0
    fi
  done
  fail "invalid selection: $reply"
}

prompt_value() {
  local prompt="$1" default_value="$2" value
  if use_gum; then
    value="$(gum input --prompt "${prompt}: " --value "$default_value")" || return 1
    printf '%s\n' "$value"
    return 0
  fi
  if [[ -n "$default_value" ]]; then
    printf '%s [%s]: ' "$prompt" "$default_value" >&2
  else
    printf '%s: ' "$prompt" >&2
  fi
  IFS= read -r value || return 1
  if [[ -z "$value" ]]; then
    printf '%s\n' "$default_value"
  else
    printf '%s\n' "$value"
  fi
}

show_startup() {
  cat <<EOF
Install wizard
selected environment: ${ENVIRONMENT}
AWS profile: ${AWS_PROFILE_NAME}
AWS deployer profile: ${DEPLOYER_PROFILE}
Expected AWS account: ${EXPECTED_AWS_ACCOUNT_ID}
AWS region: ${AWS_REGION_NAME}
Snowflake connection: ${SNOW_CONNECTION}
Mode: preview-first, non-deploying by default
No real infrastructure will be deployed unless you confirm an apply stage.
EOF
}

confirm_environment() {
  if confirm "Continue with selected environment ${ENVIRONMENT}?"; then
    return 0
  fi
  echo "Declined selected environment ${ENVIRONMENT}; exiting without mutation."
  exit 0
}

run_tui_wizard() {
  local old_env old_aws_default old_snow_default selected deploy_mode

  offer_gum_install

  echo "EdgarTools install TUI"
  echo "Run with one command: bash infra/scripts/install.sh"
  echo "Default action is preview-only plan; deploy apply requires explicit selection and per-stage confirmations."
  echo

  selected="$(choose_one "Select operation" "plan" "doctor" "init" "plan" "deploy" "report")"
  COMMAND="$selected"

  old_env="$ENVIRONMENT"
  old_aws_default="aws-admin-${old_env}"
  # Free-text, not a dev|prod pick-list: environments are operator-chosen slugs.
  ENVIRONMENT="$(prompt_value "Environment slug" "$ENVIRONMENT")"
  validate_env_slug "$ENVIRONMENT"
  if [[ "$AWS_PROFILE_NAME" == "$old_aws_default" ]]; then
    AWS_PROFILE_NAME="aws-admin-${ENVIRONMENT}"
  fi
  refresh_config

  AWS_PROFILE_NAME="$(prompt_value "AWS admin/provisioning profile" "$AWS_PROFILE_NAME")"
  DEPLOYER_PROFILE="$(prompt_value "AWS application deployer profile" "$DEPLOYER_PROFILE")"
  if [[ -z "$EXPECTED_AWS_ACCOUNT_ID" ]]; then
    EXPECTED_AWS_ACCOUNT_ID="$(prompt_value "Expected 12-digit AWS account ID" "")"
  fi
  AWS_REGION_NAME="$(prompt_value "AWS region" "$AWS_REGION_NAME")"
  SNOW_CONNECTION="$(prompt_value "Snowflake connection" "$SNOW_CONNECTION")"
  [[ -n "$SNOW_CONNECTION" ]] || fail "Snowflake connection is required (no default is derived from the environment slug)"
  WORKSPACE="$(prompt_value "Local wizard workspace" "$WORKSPACE")"

  if [[ "$COMMAND" == "report" ]]; then
    REPORT_FILE="$(prompt_value "Report file (blank for auto timestamped report)" "${REPORT_FILE:-}")"
  fi

  if [[ "$COMMAND" == "deploy" ]]; then
    if [[ "$APPLY" == "true" ]]; then
      deploy_mode="$(choose_one "Select deploy mode" "apply with per-stage confirmations" "preview only" "apply with per-stage confirmations")"
    else
      deploy_mode="$(choose_one "Select deploy mode" "preview only" "preview only" "apply with per-stage confirmations")"
    fi
    case "$deploy_mode" in
      apply*) APPLY=true ;;
      *) APPLY=false ;;
    esac
  else
    APPLY=false
  fi

  refresh_config
}

shell_quote() {
  local value="$1"
  printf "'%s'" "$(printf '%s' "$value" | sed "s/'/'\\\\''/g")"
}

redact_text() {
  sed -E \
    -e "s#postgres(ql)?://[^[:space:]]+#<redacted-dsn>#g" \
    -e "s#s3://[^[:space:]]+#<redacted-s3-url>#g" \
    -e "s#arn:aws[^[:space:]\"']+#<redacted-arn>#g" \
    -e "s#sha256:[0-9a-fA-F]{32,}#<redacted-image-digest>#g" \
    -e "s#([Ee][Xx][Tt][Ee][Rr][Nn][Aa][Ll][ _-]?[Ii][Dd][^A-Za-z0-9]+)[A-Za-z0-9._:/=-]+#\1<redacted-external-id>#g" \
    -e "s#([Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]|[Tt][Oo][Kk][Ee][Nn]|[Ss][Ee][Cc][Rr][Ee][Tt]|[Aa][Pp][Ii][_-]?[Kk][Ee][Yy])([=:])('[^']*'|\"[^\"]*\"|[^[:space:]]+)#\1\2<redacted>#g" \
    -e "s#\"(snowflake_admin|application|admin_password|password)\"[[:space:]]*:[[:space:]]*\"[^\"]*\"#\"\1\": \"<redacted>\"#g" \
    -e "s#(^|[^0-9])([0-9]{12})([^0-9]|$)#\1<redacted-account-id>\3#g"
}

ensure_workspace() {
  mkdir -p "${WORKSPACE}/reports" "${WORKSPACE}/setup/${ENVIRONMENT}"
}

template_paths() {
  cat <<EOF
infra/terraform/bootstrap-state/terraform.tfvars.example
infra/terraform/accounts/${ENVIRONMENT}/backend.hcl.example
infra/terraform/accounts/${ENVIRONMENT}/terraform.tfvars.example
infra/terraform/access/aws/accounts/${ENVIRONMENT}/backend.hcl.example
infra/terraform/access/aws/accounts/${ENVIRONMENT}/terraform.tfvars.example
infra/terraform/snowflake/accounts/${ENVIRONMENT}/backend.hcl.example
infra/terraform/snowflake/accounts/${ENVIRONMENT}/terraform.tfvars.example
infra/terraform/access/snowflake/accounts/${ENVIRONMENT}/backend.hcl.example
infra/terraform/access/snowflake/accounts/${ENVIRONMENT}/terraform.tfvars.example
infra/snowflake/dbt/edgartools_gold/profiles.yml.example
EOF
}

expected_config_paths() {
  cat <<EOF
infra/terraform/bootstrap-state/terraform.tfvars
infra/terraform/accounts/${ENVIRONMENT}/backend.hcl
infra/terraform/accounts/${ENVIRONMENT}/terraform.tfvars
infra/terraform/access/aws/accounts/${ENVIRONMENT}/backend.hcl
infra/terraform/access/aws/accounts/${ENVIRONMENT}/terraform.tfvars
infra/terraform/snowflake/accounts/${ENVIRONMENT}/backend.hcl
infra/terraform/snowflake/accounts/${ENVIRONMENT}/terraform.tfvars
infra/terraform/access/snowflake/accounts/${ENVIRONMENT}/backend.hcl
infra/terraform/access/snowflake/accounts/${ENVIRONMENT}/terraform.tfvars
infra/snowflake/dbt/edgartools_gold/profiles.yml
EOF
}

application_manifest_value() {
  local key="$1" file="${REPO_ROOT}/infra/aws-${ENVIRONMENT}-application.json"
  [[ -f "$file" ]] || return 1
  python3 - "$file" "$key" <<'PY'
import json
import sys

path, dotted_key = sys.argv[1:3]
try:
    value = json.loads(open(path, encoding="utf-8").read())
except Exception:
    raise SystemExit(1)

for part in dotted_key.split("."):
    if not isinstance(value, dict) or part not in value:
        raise SystemExit(1)
    value = value[part]

if not isinstance(value, str):
    raise SystemExit(1)
print(value)
PY
}

known_install_notes_markdown() {
  cat <<'EOF'
- `bronze_seed_silver_gold` now needs the Step Functions `batch_size` input defaulted and stringified before ECS `ContainerOverrides.Command`; older deployed definitions can fail immediately in `SeedFromBronze`.
- Fresh silver stores may not contain the legacy `sec_tracked_universe` table; table-count reporting must treat that missing table as zero so `seed-bronze-batches` can finish after writing the CIK batch manifest.
- First-time copied-bronze loads may not have `warehouse/silver/sec/shard-manifest.json`; `bootstrap-batch` and `mdm mastering`'s silver reader both fall back to the monolith `silver.duckdb` when no shard manifest exists yet (write side: `warehouse_orchestrator.py`'s `shard_manifest_missing_monolith_fallback`; read side: `mdm/cli.py`'s `_silver_reader()`). Because all concurrent batches in this fallback mode write to the same single monolith file, `BatchSilver`'s `MaxConcurrency` is a write-race risk lever, not just a throughput one. `MaxConcurrency=2` was validated end-to-end in prod (run `bronze-seed-silver-gold-1782351277`, 2026-06-24/25: `SeedFromBronze` → `BatchSilver` (zero `sec_pull_started`) → `Mastering` → `Infer Relationships` → `Publish Relationships` → `Reconcile` → `GoldRefresh` all `SUCCEEDED`). Current source is `MaxConcurrency=4`, which is **unvalidated** -- watch the next live run closely for monolith write contention (DuckDB lock errors, partial/duplicate rows) before trusting it.
- `bootstrap-batch`'s idempotency check only consulted the silver checkpoint table, not S3 bronze existence directly -- on a fresh silver DB this caused real per-CIK SEC API calls during `BatchSilver` despite the bronze already existing in S3 (confirmed live: ~1 batch/hour with live `sec_pull_started` events). Fixed via a CIK-prefix glob fallback (`StorageLocation.find_existing`) and PR95's `merge_filings` bulk-upsert path. Always publish and deploy a fresh warehouse image that contains PR95 before using the one-click stage, and verify a `bronze_seed_silver_gold` run's first batch shows zero `sec_pull_started` events in CloudWatch within minutes of starting -- don't wait an hour to check.
- Do not treat `BatchSilver` succeeding as proof the whole chain works: the first time this chain ever reached `Mastering` in prod, it failed separately (read-side shard-manifest-missing bug, distinct from the write-side bug above). Do not flip Blocker 4 / hosted graph E2E to PASS until `SeedFromBronze`, `BatchSilver`, `Mastering`, `Infer Relationships`, `Publish Relationships`, `Reconcile`, and `GoldRefresh` all succeed in prod and the run shows zero `sec_pull_started` events during `BatchSilver`.
- **Do not redrive a failed `bronze_seed_silver_gold` execution after deploying a fix.** AWS Step Functions pins a redriven execution to the exact task-definition revision that was active when that execution last reached the failed state -- it does NOT pick up newly deployed revisions. Confirmed live: redriving after deploying a fix still ran the OLD task-definition revision and reproduced the OLD failure. Always start a fresh execution to pick up a new image/fix; only redrive when no relevant image has changed since the failure (e.g. a transient network blip) and you want to skip re-running already-succeeded `BatchSilver` batches.
- `deploy-aws-application.sh --enable-mdm` silently defaults MDM task definitions to the *warehouse* image ref when `--mdm-image-ref` is omitted -- they need different images (MDM installs `.[s3,mdm-runtime]`, warehouse installs `.[s3]`). Always pass `--mdm-image-ref` explicitly; the install wizard's stages now do this automatically by publishing and resolving both image refs separately.
- `cleanup-ecr-images.sh` only protects image digests referenced by *currently active* ECS task definitions. If you redeploy with a stale cached image ref (e.g. from an old `infra/aws-<env>-application.json` or a manually-typed digest) and then run cleanup, the digest you're about to deploy can be deleted out from under you if it isn't the one already active. Always redeploy with a freshly published or freshly verified-present image ref before running ECR cleanup, not after assuming an old digest is still around.
- `sec_platform_runner_step_functions` needs `states:RedriveExecution` (in addition to `StartExecution`/`DescribeExecution`/`StopExecution`) for redrive to work at all -- this was missing and is now in Terraform (`infra/terraform/access/aws/modules/runtime_access/main.tf`). If a redrive call fails with an IAM authorization error, check this policy is actually applied (`terraform apply` in `infra/terraform/access/aws/accounts/<env>/`, not a CLI-only patch that can drift from source).
EOF
}

copy_templates_to_workspace() {
  local rel src dest
  while IFS= read -r rel; do
    src="${REPO_ROOT}/${rel}"
    [[ -f "$src" ]] || continue
    dest="${WORKSPACE}/setup/${ENVIRONMENT}/${rel}"
    mkdir -p "$(dirname "$dest")"
    cp -n "$src" "$dest"
    echo "Copied template: ${rel} -> ${dest#${REPO_ROOT}/}"
  done < <(template_paths)
}

CHECK_NAMES=()
CHECK_STATUSES=()
CHECK_DETAILS=()
CHECK_FAILURES=0

add_check() {
  local name="$1" status="$2" detail="$3"
  CHECK_NAMES+=("$name")
  CHECK_STATUSES+=("$status")
  CHECK_DETAILS+=("$detail")
  [[ "$status" == "fail" ]] && CHECK_FAILURES=$((CHECK_FAILURES + 1))
  return 0
}

check_command_available() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    add_check "tool:${name}" "pass" "${name} found"
  else
    add_check "tool:${name}" "fail" "${name} not found on PATH"
  fi
}

run_checks() {
  local rel missing_templates missing_configs dirty account_id identity_value expected_bucket bucket image_ref
  CHECK_NAMES=()
  CHECK_STATUSES=()
  CHECK_DETAILS=()
  CHECK_FAILURES=0

  check_command_available bash
  check_command_available git
  check_command_available uv
  check_command_available aws
  check_command_available snow
  check_command_available terraform
  check_command_available docker

  if command -v aws >/dev/null 2>&1; then
    if aws --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION_NAME" sts get-caller-identity --output json >/dev/null 2>&1; then
      add_check "aws identity" "pass" "AWS CLI identity resolved for selected profile and region"
    else
      add_check "aws identity" "fail" "AWS CLI identity check failed for selected profile and region"
    fi
    account_id="$(selected_aws_account_id 2>/dev/null || true)"
    if [[ "$account_id" == "$EXPECTED_AWS_ACCOUNT_ID" ]]; then
      add_check "expected AWS account" "pass" "AWS caller matches the requested account"
    else
      add_check "expected AWS account" "fail" "AWS account mismatch; expected ${EXPECTED_AWS_ACCOUNT_ID}"
    fi
  fi

  if [[ "$ENVIRONMENT" == "prod" && "$AWS_REGION_NAME" != "us-east-1" ]]; then
    add_check "canonical prod region" "fail" "production region must be us-east-1"
  fi

  if [[ "$ENVIRONMENT" == "prod" && -n "${EDGAR_IDENTITY:-}" && ! "${EDGAR_IDENTITY}" =~ [^[:space:]@]+@[^[:space:]@]+ ]]; then
    add_check "EDGAR identity" "fail" "EDGAR_IDENTITY is set but does not contain a contact email"
  elif [[ -n "${EDGAR_IDENTITY:-}" ]]; then
    add_check "EDGAR identity" "pass" "EDGAR_IDENTITY contains a contact email"
  else
    add_check "EDGAR identity" "warn" "EDGAR_IDENTITY is not set; bounded SEC smoke stages cannot run"
  fi

  if command -v snow >/dev/null 2>&1; then
    if snow connection test --connection "$SNOW_CONNECTION" >/dev/null 2>&1; then
      add_check "snow connection" "pass" "SnowCLI connection test succeeded"
    else
      add_check "snow connection" "fail" "SnowCLI connection test failed"
    fi
  fi

  if command -v terraform >/dev/null 2>&1; then
    if terraform version >/dev/null 2>&1; then
      add_check "terraform availability" "pass" "terraform version returned successfully"
    else
      add_check "terraform availability" "fail" "terraform version failed"
    fi
  fi

  if command -v docker >/dev/null 2>&1; then
    if docker version >/dev/null 2>&1; then
      add_check "docker availability" "pass" "docker client/daemon version returned successfully"
    else
      add_check "docker availability" "warn" "docker command exists but daemon/version check failed"
    fi
  fi

  if git -C "$REPO_ROOT" rev-parse --show-toplevel >/dev/null 2>&1; then
    dirty="$(git -C "$REPO_ROOT" status --short 2>/dev/null || true)"
    if [[ -n "$dirty" ]]; then
      add_check "repo safety" "warn" "working tree has local changes; avoid overlapping ownership before apply"
    else
      add_check "repo safety" "pass" "working tree is clean"
    fi
  else
    add_check "repo safety" "fail" "not running inside a git repository"
  fi

  missing_templates=""
  while IFS= read -r rel; do
    [[ -f "${REPO_ROOT}/${rel}" ]] || missing_templates="${missing_templates} ${rel}"
  done < <(template_paths)
  if [[ -z "$missing_templates" ]]; then
    add_check "config templates" "pass" "expected example templates are present"
  else
    add_check "config templates" "fail" "missing example templates:${missing_templates}"
  fi

  missing_configs=""
  while IFS= read -r rel; do
    [[ -f "${REPO_ROOT}/${rel}" ]] || missing_configs="${missing_configs} ${rel}"
  done < <(expected_config_paths)
  if [[ -z "$missing_configs" ]]; then
    add_check "local config files" "pass" "expected ignored local config files are present"
  else
    add_check "local config files" "warn" "missing ignored local config files:${missing_configs}"
  fi

  # The application summary is generated and gitignored. It does not survive
  # a fresh checkout, but is still needed for the production bucket checks.
  if [[ -f "${REPO_ROOT}/infra/aws-${ENVIRONMENT}-application.json" ]]; then
    add_check "prod application summary" "pass" "infra/aws-${ENVIRONMENT}-application.json present"
    if [[ "$ENVIRONMENT" == "prod" ]]; then
      for bucket in bronze_bucket_name warehouse_bucket_name snowflake_export_bucket_name; do
        expected_bucket="edgartools-prod-${bucket%_bucket_name}-${EXPECTED_AWS_ACCOUNT_ID}"
        [[ "$bucket" == "snowflake_export_bucket_name" ]] && expected_bucket="edgartools-prod-snowflake-export-${EXPECTED_AWS_ACCOUNT_ID}"
        if [[ "$(application_manifest_value "$bucket" 2>/dev/null || true)" == "$expected_bucket" ]]; then
          add_check "canonical ${bucket}" "pass" "manifest uses canonical production bucket"
        else
          add_check "canonical ${bucket}" "fail" "manifest does not use ${expected_bucket}"
        fi
      done
    fi
  else
    add_check "prod application summary" "warn" "infra/aws-${ENVIRONMENT}-application.json missing; regenerate via the 'AWS: ECS task definitions' stage"
  fi


  for image_ref in "${REPO_ROOT}/infra/aws-${ENVIRONMENT}-warehouse-image-ref.txt" "${REPO_ROOT}/infra/aws-${ENVIRONMENT}-mdm-image-ref.txt"; do
    if [[ -s "$image_ref" ]]; then
      add_check "image:$(basename "$image_ref")" "pass" "resolved image reference is available"
    else
      add_check "image:$(basename "$image_ref")" "warn" "image reference missing; publish stage is required before application deployment"
    fi
  done

  if [[ "$ENVIRONMENT" == "prod" && -x "${REPO_ROOT}/infra/scripts/preflight-prod-promotion.sh" ]]; then
    add_check "promotion preflight" "pass" "read-only canonical production preflight is available"
  fi
}

print_checks() {
  local i detail
  echo "Doctor checks:"
  for i in "${!CHECK_NAMES[@]}"; do
    detail="$(printf '%s' "${CHECK_DETAILS[$i]}" | redact_text)"
    printf '  %-24s %-5s %s\n' "${CHECK_NAMES[$i]}" "${CHECK_STATUSES[$i]}" "$detail"
  done
}

STAGE_NAMES=()
STAGE_DESCRIPTIONS=()
STAGE_COMMANDS=()

add_stage() {
  STAGE_NAMES+=("$1")
  STAGE_DESCRIPTIONS+=("$2")
  STAGE_COMMANDS+=("$3")
}

build_stages() {
  local aws_profile_q region_q deployer_q expected_account_q env_q snow_q image_tag db_name
  local mdm_instance_name mdm_network_policy_name mdm_network_rule_name mdm_schema_name
  local mdm_instance_name_q mdm_network_policy_name_q mdm_network_rule_name_q mdm_schema_name_q mdm_comment_env_q
  STAGE_NAMES=()
  STAGE_DESCRIPTIONS=()
  STAGE_COMMANDS=()
  aws_profile_q="$(shell_quote "$AWS_PROFILE_NAME")"
  region_q="$(shell_quote "$AWS_REGION_NAME")"
  deployer_q="$(shell_quote "$DEPLOYER_PROFILE")"
  expected_account_q="$(shell_quote "$EXPECTED_AWS_ACCOUNT_ID")"
  env_q="$(shell_quote "$ENVIRONMENT")"
  snow_q="$(shell_quote "$SNOW_CONNECTION")"
  db_name="$SNOWFLAKE_DATABASE"
  image_tag="sha-$(git -C "$REPO_ROOT" rev-parse --short=12 HEAD 2>/dev/null || echo HEAD)"
  mdm_instance_name="${db_name}_MDM"
  mdm_network_policy_name="edgartools_${ENVIRONMENT}_mdm_postgres_policy"
  mdm_network_rule_name="mdm_postgres_ingress_all"
  mdm_schema_name="${db_name}.MDM"
  mdm_instance_name_q="$(shell_quote "$mdm_instance_name")"
  mdm_network_policy_name_q="$(shell_quote "$mdm_network_policy_name")"
  mdm_network_rule_name_q="$(shell_quote "$mdm_network_rule_name")"
  mdm_schema_name_q="$(shell_quote "$mdm_schema_name")"
  mdm_comment_env_q="$(shell_quote "$ENVIRONMENT")"

  # Phase: provision -- bare AWS/Snowflake infrastructure and schema; no
  # application artifacts (images, task defs, dbt models) and no real data.
  # See .scratch/install-sh-provision-deploy-data/map.md (wayfinder ticket 04):
  # this phase grouping is a physical reorder of what used to be one flat
  # sequential list, not just a label -- every stage below actually runs in
  # this order now. Ticket 01 decided the classification; Ticket 02 verified
  # no inter-stage dependency breaks under it.
  add_stage \
    "AWS: Terraform state bucket" \
    "Remote state bootstrap for the AWS Terraform backend. Passes environment and terraform_state_bucket_name explicitly rather than relying on this root's own local terraform.tfvars: that file is not env-name-aware (it predates the dev|prod-enum-to-slug rename, wayfinder ticket 03), so an operator's leftover local file for a different/earlier environment would otherwise silently bootstrap (or attempt to recreate) the wrong bucket." \
    "cd infra/terraform/bootstrap-state
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform init
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform plan -var 'environment=${ENVIRONMENT}' -var 'terraform_state_bucket_name=edgartools-${ENVIRONMENT}-tfstate-${expected_account_q}'
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform apply -var 'environment=${ENVIRONMENT}' -var 'terraform_state_bucket_name=edgartools-${ENVIRONMENT}-tfstate-${expected_account_q}'"

  add_stage \
    "Snowflake: Neo4j Native App install" \
    "Installs the Neo4j Graph Analytics Native App, which nothing in this repo previously did: infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql (run by the 'MDM + graph: connectivity, migrations, sync, verification' stage below) only GRANTs against an application it assumes already exists, so every prior install silently depended on someone having installed it out of band -- an assumption that does not hold for a brand-new account. Placed this early deliberately (wayfinder ticket 05): installing requires a one-time, per-organization ORGADMIN acceptance of the Snowflake Provider and Consumer Terms in Snowsight, which wayfinder ticket 02 established has no SQL or API equivalent. Running it here means that human step is in flight while the AWS and Snowflake stages that do not depend on it proceed, instead of stalling the wizard mid-run. Idempotent: exits cleanly if the application is already installed. The Marketplace listing is resolved at run time rather than hardcoded, because ticket 02's candidate global name was transcribed from a guide URL rather than read off SHOW AVAILABLE LISTINGS and is explicitly unverified. NOTE: this stage is necessary but not sufficient for the graph half of a brand-new environment -- the later grants stage grants against {{ database }}.NEO4J_GRAPH_MIGRATION, a schema that mdm publish-relationships does not create until the 'MDM + graph: connectivity, migrations, sync, verification' stage runs, so on a genuinely new account the grants stage still runs ahead of its own prerequisite. See wayfinder ticket 07. Its position within the provision phase is otherwise unpinned (install-sh-provision-deploy-data map, Ticket 01) -- it only needs to precede the Postgres/graph prerequisites stage below, not literally be the second stage." \
    "bash infra/scripts/install-neo4j-graph-app.sh --snow-connection ${SNOW_CONNECTION}"

  add_stage \
    "AWS: passive infrastructure" \
    "VPC, S3 bronze/warehouse/export buckets, S3 endpoint, ECR, ECS cluster, CloudWatch logs, SNS, KMS, and empty Secrets Manager containers." \
    "cd infra/terraform/accounts/${ENVIRONMENT}
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform init -backend-config=backend.hcl
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform plan
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform apply"

  add_stage \
    "AWS: access roles/policies" \
    "AWS access Terraform for deployer, runner execution/task roles, and scoped policies. Applies in bootstrap mode (snowflake_bootstrap_enabled=true, snowflake_state_bucket=null) rather than a bare apply: a bare apply would let this root's own local terraform.tfvars supply snowflake_manifest_subscriber_arn via a cross-state read of whatever Snowflake state key that file happens to reference -- stale after any account swap (see snowflake-account-cutover map's addendum) -- silently granting SNS trust to the wrong Snowflake account's AWS principal instead of the wildcard bootstrap trust this stage is meant to establish. The 'Snowflake: native-pull foundation' stage below (deploy-snowflake-stack.sh) re-applies this exact root twice more afterward -- once to read the real principal, once to reconcile trust down to it exactly -- so this stage's job is only to get the deployer/runner IAM roles into existence with safe placeholder trust, not to get the final Snowflake trust value right." \
    "cd infra/terraform/access/aws/accounts/${ENVIRONMENT}
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform init -backend-config=backend.hcl
_aws_access_bootstrap_overlay=\"\$(mktemp).tfvars.json\"
mv \"\${_aws_access_bootstrap_overlay%.tfvars.json}\" \"\${_aws_access_bootstrap_overlay}\"
printf '%s' '{\"snowflake_bootstrap_enabled\": true, \"snowflake_manifest_subscriber_arn\": null, \"snowflake_storage_external_id\": \"edgartools-${ENVIRONMENT}-snowflake-native-pull\", \"snowflake_state_bucket\": null}' > \"\${_aws_access_bootstrap_overlay}\"
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform plan -var-file=\"\${_aws_access_bootstrap_overlay}\"
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform apply -var-file=\"\${_aws_access_bootstrap_overlay}\"
rm -f \"\${_aws_access_bootstrap_overlay}\""

  add_stage \
    "Snowflake: native-pull foundation" \
    "baseline database/schemas/warehouses plus native-pull integration, stage, source tables, pipe, stream, procedures, task, and access grants." \
    "SNOW_CONNECTION=${snow_q} bash infra/scripts/deploy-snowflake-stack.sh --env-name ${ENVIRONMENT} --snow-connection ${SNOW_CONNECTION} --run-validation"

  add_stage \
    "Snowflake: fundamentals load wrapper" \
    "Creates LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN, the composite-key load wrapper Branch B passthrough fundamentals tables (SEC_FINANCIAL_FACT, SEC_THIRTEENF_HOLDING, and siblings) need -- a separate procedure from LOAD_EXPORTS_FOR_RUN because those tables have composite natural keys, not LOAD_EXPORTS_FOR_RUN's single-scalar-key assumption (06_fundamentals_load_wrapper.sql's own header, Q7-7b decision). Unlike 01-05 (source stage/refresh status/load wrapper/refresh wrapper/refresher keypair), which native_pull's Terraform module (snowflake_execute.source_load_procedure/refresh_procedure/stream_processor_procedure, snowflake_task.manifest_processor -- applied by the 'Snowflake: native-pull foundation' stage above) already creates and 05 explicitly marks deprecated, this procedure has zero Terraform coverage -- confirmed via repo-wide search for LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN. Never wired into any install/deploy script before this stage. Must run after native-pull foundation (needs EDGARTOOLS_SOURCE to already exist); uses the same session-variable pattern as the (now Terraform-superseded) 03_source_load_wrapper.sql it mirrors." \
    "{ printf '%s\n' \"SET database_name = '${db_name}';\" \"SET source_schema_name = 'EDGARTOOLS_SOURCE';\" \"SET deployer_role_name = 'ACCOUNTADMIN';\" \"SET fundamentals_load_procedure_name = 'LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN';\"
cat infra/snowflake/sql/bootstrap/06_fundamentals_load_wrapper.sql; } | snow sql --connection ${SNOW_CONNECTION} -i"

  add_stage \
    "Snowflake Postgres / graph prerequisites" \
    "Creates the MDM schema and its Snowflake Postgres network policy/instance (wayfinder snowflake-account-cutover ticket 03), then delegates credential rotation, migration, and AWS secret bootstrap to the maintained bootstrap script. Finishes wiring the mdm_schema_name/mdm_network_policy_name/mdm_network_rule_name values this function already computed but, before this change, never referenced. The Neo4j grants SQL that used to run here has moved to the first line of the 'MDM + graph: connectivity...' stage below (wayfinder ticket 01): it grants against {{ database }}.NEO4J_GRAPH_MIGRATION, a schema mdm publish-relationships doesn't create until that later stage runs, so it needs to run there, not here." \
    "snow sql --connection ${SNOW_CONNECTION} -q \"CREATE SCHEMA IF NOT EXISTS ${mdm_schema_name};\"
snow sql --connection ${SNOW_CONNECTION} --enable-templating JINJA --filename infra/snowflake/postgres/mdm_create_network_policy.sql -D schema=${mdm_schema_name} -D network_rule_name=${mdm_network_rule_name} -D network_policy_name=${mdm_network_policy_name}
snow sql --connection ${SNOW_CONNECTION} --enable-templating JINJA --filename infra/snowflake/postgres/mdm_create_instance.sql -D instance_name=${mdm_instance_name} -D network_policy=${mdm_network_policy_name} -D comment_env=${ENVIRONMENT}
bash infra/scripts/bootstrap-prod-mdm.sh --env-name ${ENVIRONMENT} --snow-connection ${SNOW_CONNECTION} --instance-name ${mdm_instance_name_q} --aws-profile ${AWS_PROFILE_NAME} --aws-region ${AWS_REGION_NAME} --name-prefix edgartools-${ENVIRONMENT}"

  add_stage \
    "Snowflake: installer role" \
    "Creates EDGARTOOLS_PROD_INSTALLER (19_installer_role.sql), a dedicated least-privilege role for install.sh's own schema-bootstrap stages, so they stop running as ACCOUNTADMIN by default -- the same 'everything owned by the all-powerful connection role' shape CLAUDE.md already documents for the original Streamlit dashboard. Scope is deliberately surgical, not total (change-propagation map, Ticket 30 follow-up, 2026-08-26): only schema-bootstrap files that are fully self-contained -- create a new schema, populate it, grant only on objects the creating role itself then owns -- were converted to run as this role; currently just 09_mdm_mirror_schema.sql (next stage). Files containing a statement that grants a privilege on an object this role wouldn't own (a database- or account-level grant, CREATE ROLE, or a grant on a pre-existing Terraform/deployer-owned object) stay on ACCOUNTADMIN -- see 19_installer_role.sql's own header for the itemized list, including why 11_silver_landing_schema.sql was deliberately left out: its own header already documents a considered, pre-existing decision against minting a second pipeline-object-owner role, which this new role would otherwise repeat there. Must run after 'Snowflake Postgres / graph prerequisites' above (needs the database to already exist) and before every stage below that references EDGARTOOLS_PROD_INSTALLER." \
    "snow sql --connection ${SNOW_CONNECTION} -f infra/snowflake/sql/bootstrap/19_installer_role.sql"

  add_stage \
    "Snowflake: MDM mirror + graph schema" \
    "Creates the 19 MDM Postgres-mirror tables in ${db_name}.MDM (09_mdm_mirror_schema.sql, now running as EDGARTOOLS_PROD_INSTALLER -- see the 'Snowflake: installer role' stage above) and the NEO4J_GRAPH_MIGRATION graph destination schema plus its CREATE-SCHEMA-ON-DATABASE grant (10_graph_schema.sql, still ACCOUNTADMIN -- that database-level grant is exactly the kind of statement the installer role deliberately doesn't cover; then re-applies the Neo4j Native App grants against that same schema) -- all three previously created only by an uncommitted manual shell session during the original go-live cutover, so a fresh account rebuild silently came back with an empty MDM schema and no graph schema at all (CLAUDE.md's 'MDM Snowflake mirror schema lost on cutover' incident; reproduced live 2026-08-22 while writing this stage -- ${db_name}.MDM had zero tables and ${db_name}.NEO4J_GRAPH_MIGRATION did not exist at all, both blocking a live bronze_seed_silver_gold execution's Publish/Publish Relationships steps until fixed by hand). Must run after 'Snowflake: installer role' above and 'Snowflake Postgres / graph prerequisites' further above, which creates the MDM schema itself but not its tables. Running the Native App grants here too (ahead of the 'MDM + graph: connectivity...' stage's own, still-idempotent re-application further below) corrects that later stage's own comment, which assumed 'mdm publish-relationships' creates NEO4J_GRAPH_MIGRATION on its own -- it can't: CREATE SCHEMA IF NOT EXISTS evaluates the CREATE SCHEMA privilege before checking existence, so EDGARTOOLS_${ENV_UPPER}_LOADER needs that grant (applied here) before it can create the schema at all, not just before its later grants can be re-applied." \
    "snow sql --connection ${SNOW_CONNECTION} -f infra/snowflake/sql/bootstrap/09_mdm_mirror_schema.sql
snow sql --connection ${SNOW_CONNECTION} -f infra/snowflake/sql/bootstrap/10_graph_schema.sql
snow sql --connection ${SNOW_CONNECTION} --enable-templating JINJA --filename infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql -D database=${db_name}"

  # Phase: deploy -- application artifacts (images, ECS task defs, dbt gold
  # models, ownership/grants that depend on those models existing, the
  # Streamlit dashboard). No real SEC data is fetched in this phase.
  add_stage \
    "AWS: ECR image publish" \
    "Publishes the warehouse AND MDM images to AWS ECR with dev and immutable rollback/audit tags. Writes both resolved digest-pinned image refs to local files so the next stage can pick them up automatically. Publishing both here (not just warehouse) is required: deploy-aws-application.sh silently defaults the MDM task definitions to the warehouse image ref when --mdm-image-ref is omitted, which is wrong (MDM has different runtime deps, .[s3,mdm-runtime] vs .[s3]) and was hit live in production on 2026-06-23. Both roles publish to the same consolidated edgartools-<env>-images repository (CLAUDE.md's 'Image management' section) -- the old per-role edgartools-<env>-warehouse/-mdm repos this stage used before this fix are a read-only rollback archive nothing pushes to anymore; confirmed live (aws ecr describe-repositories) that only the consolidated repo exists in this account, so the pre-fix stage would have failed outright with RepositoryNotFoundException." \
    "AWS_PROFILE=${deployer_q} bash infra/scripts/publish-warehouse-image.sh --aws-region ${AWS_REGION_NAME} --ecr-repository edgartools-${ENVIRONMENT}-images --role warehouse --image-tag ${image_tag} --mode auto --cache-from-tag ${ENVIRONMENT} --also-tag ${ENVIRONMENT} --output-file infra/aws-${ENVIRONMENT}-warehouse-image-ref.txt
AWS_PROFILE=${deployer_q} bash infra/scripts/publish-warehouse-image.sh --aws-region ${AWS_REGION_NAME} --ecr-repository edgartools-${ENVIRONMENT}-images --role mdm --image-tag ${image_tag} --mode auto --cache-from-tag ${ENVIRONMENT} --also-tag ${ENVIRONMENT} --output-file infra/aws-${ENVIRONMENT}-mdm-image-ref.txt"

  add_stage \
    "AWS: ECS task definitions" \
    "Registers ECS task definitions for the locally qualified image and wires application CloudWatch logs. Legacy Step Functions remain disabled pending source/feed qualification. Auto-resolves both image refs from the ECR publish stage's output files; falls back to WAREHOUSE_IMAGE_REF/MDM_IMAGE_REF only if those files are missing. Always passes --mdm-image-ref explicitly and --enable-mdm." \
    "warehouse_image_ref_file=\"infra/aws-${ENVIRONMENT}-warehouse-image-ref.txt\"
mdm_image_ref_file=\"infra/aws-${ENVIRONMENT}-mdm-image-ref.txt\"
if [[ -s \"\${warehouse_image_ref_file}\" ]]; then
  resolved_warehouse_image_ref=\"\$(cat \"\${warehouse_image_ref_file}\")\"
else
  resolved_warehouse_image_ref=\"\${WAREHOUSE_IMAGE_REF:?set WAREHOUSE_IMAGE_REF, or run the ECR image publish stage first so \${warehouse_image_ref_file} is created}\"
fi
if [[ -s \"\${mdm_image_ref_file}\" ]]; then
  resolved_mdm_image_ref=\"\$(cat \"\${mdm_image_ref_file}\")\"
else
  resolved_mdm_image_ref=\"\${MDM_IMAGE_REF:?set MDM_IMAGE_REF, or run the ECR image publish stage first so \${mdm_image_ref_file} is created}\"
fi
AWS_PROFILE=${deployer_q} bash infra/scripts/deploy-aws-application.sh --env ${ENVIRONMENT} --aws-profile ${DEPLOYER_PROFILE} --aws-account-id ${expected_account_q} --aws-region ${AWS_REGION_NAME} --skip-build --image-ref \"\${resolved_warehouse_image_ref}\" --mdm-image-ref \"\${resolved_mdm_image_ref}\" --enable-mdm --output-file infra/aws-${ENVIRONMENT}-application.json"

  add_stage \
    "Snowflake: MDM export targets" \
    "Creates the 5 MDM golden-record export target tables (MDM_COMPANY_ENTITY, MDM_ADVISER, MDM_PERSON, MDM_SECURITY, MDM_FUND) that edgar_warehouse/mdm/export.py's MDMExporter.export_pending() MERGEs into -- no Terraform equivalent creates these (wayfinder snowflake-account-cutover ticket 07). Must run before the next stage: company.sql (dbt) reads {{ source('mdm_export', 'MDM_COMPANY_ENTITY') }}, so a brand-new account's first dbt run would fail without this table already existing. 07_mdm_export_targets.sql uses Snowflake session variables (SET x = ...; then \$x in the SQL body), not Jinja {{ }} templating, so its required SET statements are piped in via stdin ahead of the file's own content rather than passed as -D flags." \
    "{ printf '%s\n' \"SET database_name = '${db_name}';\" \"SET gold_schema_name = 'EDGARTOOLS_GOLD';\" \"SET deployer_role_name = 'ACCOUNTADMIN';\" \"SET loader_role_name = 'EDGARTOOLS_${ENV_UPPER}_LOADER';\"
cat infra/snowflake/sql/bootstrap/07_mdm_export_targets.sql; } | snow sql --connection ${SNOW_CONNECTION} -i"

  add_stage \
    "Snowflake: MDM export deployer read" \
    "Grants EDGARTOOLS_${ENV_UPPER}_DEPLOYER read access to MDM_COMPANY_ENTITY, the same access the stage above already grants the loader role (17_mdm_export_deployer_read.sql). Must run after 'Snowflake: MDM export targets' immediately above and before 'Snowflake: dbt gold' below: a dynamic table's INITIAL refresh executes as whichever role ran dbt run -- deployer, per profiles.yml's prod target -- and company.sql's EDGARTOOLS_GOLD.COMPANY dynamic table reads MDM_COMPANY_ENTITY, so its first refresh fails with 'Object does not exist or not authorized' without this grant even though the loader role already has it. Never wired into any install/deploy script before this stage; the underlying gap this and the next stage both fix (dbt gold silently assuming it runs as the loader role) is documented directly in 16_silver_landing_deployer_read.sql's header." \
    "snow sql --connection ${SNOW_CONNECTION} -f infra/snowflake/sql/bootstrap/17_mdm_export_deployer_read.sql"

  add_stage \
    "Snowflake: silver-landing schema + ingest" \
    "Provisions EDGARTOOLS_SILVER_LANDING (11_silver_landing_schema.sql, generated verbatim from silver_store.py's DDL -- same anti-drift rationale as the MDM mirror schema stage above), EDGARTOOLS_SILVER plus MDM's dedicated silver-reader role (12_silver_schema_and_mdm_reader.sql), the landing ingest apparatus -- stage/file-format/load-procedure/scheduled task (13_silver_landing_ingest.sql), the mdm_entity_id column backfill for the 6 tables 11 created before the mdm-ahead-of-silver map's Phase A added that column to its own generator output (14_silver_landing_mdm_entity_id.sql), the Form 3/4/5 classification-evidence and joint-filing columns for tables 11 created before Person Consumer Contract ticket 19 (20_silver_landing_ownership_evidence.sql -- the three dbt ownership silver models select them, so it must run before dbt), SEC's address country_code for a table 11 created before company mastering ticket 14 (21_silver_landing_company_country_code.sql -- the dbt sec_company_address silver model selects it, so it must run before dbt), and EDGARTOOLS_${ENV_UPPER}_DEPLOYER's read grant on EDGARTOOLS_SILVER_LANDING, the same CREATE-SCHEMA-privilege-checked-before-existence gotcha as the MDM export deployer read stage above (16_silver_landing_deployer_read.sql). Run in this exact order: each file's own header states 13 must follow 11+12 (plus native_pull's already-applied storage-integration widen, infra/terraform/snowflake/accounts/${ENVIRONMENT}/main.tf's additional_storage_locations -- confirmed already committed, needs no separate stage), 14/16/20/21 must follow 11. Must run before 'Snowflake: dbt gold' below: 12's own header requires it run before the first dbt run against the silver dbt models (infra/snowflake/dbt/edgartools_gold/models/silver/, the same dbt project and dbt run invocation as the gold models -- no separate dbt stage needed), and 16 closes the same before-dbt-run privilege gap MDM export deployer read fixes for MDM_COMPANY_ENTITY. Never wired into any install/deploy script before this stage -- confirmed via repo-wide search for each of these files." \
    "snow sql --connection ${SNOW_CONNECTION} -f infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql
snow sql --connection ${SNOW_CONNECTION} -f infra/snowflake/sql/bootstrap/12_silver_schema_and_mdm_reader.sql
snow sql --connection ${SNOW_CONNECTION} -f infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql
snow sql --connection ${SNOW_CONNECTION} -f infra/snowflake/sql/bootstrap/14_silver_landing_mdm_entity_id.sql
snow sql --connection ${SNOW_CONNECTION} -f infra/snowflake/sql/bootstrap/16_silver_landing_deployer_read.sql
snow sql --connection ${SNOW_CONNECTION} -f infra/snowflake/sql/bootstrap/20_silver_landing_ownership_evidence.sql
snow sql --connection ${SNOW_CONNECTION} -f infra/snowflake/sql/bootstrap/21_silver_landing_company_country_code.sql"

  add_stage \
    "Snowflake: dbt gold" \
    "Builds and tests dbt gold dynamic-table/view models in the Snowflake analytics target." \
    "cd infra/snowflake/dbt/edgartools_gold
uv run --with dbt-snowflake dbt deps
uv run --with dbt-snowflake dbt run --target ${ENVIRONMENT}
uv run --with dbt-snowflake dbt test --target ${ENVIRONMENT}"

  add_stage \
    "Snowflake: loader role ownership" \
    "Creates EDGARTOOLS_${ENV_UPPER}_LOADER (if the access-control Terraform root did not already) and transfers ownership of the EDGARTOOLS_GOLD dynamic tables plus the 3 manifest-pipeline procedures (LOAD_EXPORTS_FOR_RUN, REFRESH_AFTER_LOAD, PROCESS_RUN_MANIFEST_STREAM) onto it -- REFRESH_AFTER_LOAD's ALTER DYNAMIC TABLE ... REFRESH requires the direct owner role, so this must run after this stage's own dbt gold prerequisite (the dynamic tables must exist before ownership of them can be granted) and before any gold-refresh (both the standalone stage and one_click_data_refresh's internal one, both later in this sequence). 08_loader_role.sql also uses Snowflake session variables, piped the same way as the MDM export targets stage above. On a genuinely brand-new account, dbt gold above already runs as this loader role (profiles.yml's prod target), so the GRANT OWNERSHIP statements here are harmless idempotent re-grants to the already-current owner; they become real ownership transfers only when re-run against an account with pre-existing drift." \
    "{ printf '%s\n' \"SET database_name = '${db_name}';\" \"SET source_schema_name = 'EDGARTOOLS_SOURCE';\" \"SET gold_schema_name = 'EDGARTOOLS_GOLD';\" \"SET admin_role_name = 'ACCOUNTADMIN';\" \"SET loader_role_name = 'EDGARTOOLS_${ENV_UPPER}_LOADER';\" \"SET loader_default_grantee = 'ACCOUNTADMIN';\" \"SET refresh_warehouse_name = 'EDGARTOOLS_${ENV_UPPER}_REFRESH_WH';\" \"SET source_load_procedure_name = 'LOAD_EXPORTS_FOR_RUN';\" \"SET refresh_procedure_name = 'REFRESH_AFTER_LOAD';\" \"SET stream_processor_procedure_name = 'PROCESS_RUN_MANIFEST_STREAM';\" \"SET manifest_stream_name = 'SNOWFLAKE_RUN_MANIFEST_STREAM';\" \"SET status_table_name = 'SNOWFLAKE_REFRESH_STATUS';\"
cat infra/snowflake/sql/bootstrap/08_loader_role.sql; } | snow sql --connection ${SNOW_CONNECTION} -i"

  add_stage \
    "Snowflake: loader read grants on silver" \
    "Grants EDGARTOOLS_${ENV_UPPER}_LOADER OPERATE + SELECT on every EDGARTOOLS_SILVER dynamic table (current and future). Must run after this stage's own loader-role prerequisite above (the role must exist first) and before any gold-refresh (both the standalone stage and one_click_data_refresh's internal one, both later in this sequence) -- without it, REFRESH_AFTER_LOAD (EXECUTE AS OWNER, running as loader) cannot refresh any gold dynamic table whose dbt model reads from silver via ref()/source() (e.g. COMPANY, FILING_ACTIVITY, TICKER_REFERENCE), because those silver dynamic tables are owned by EDGARTOOLS_${ENV_UPPER}_DEPLOYER, not loader, and 08_loader_role.sql's own grants only ever covered EDGARTOOLS_GOLD. Found live 2026-08-22 (PRJEDJU-QJB05385): this had been silently failing every scheduled SNOWFLAKE_RUN_MANIFEST_TASK refresh since at least 2026-08-18 with no visible signal beyond the task's own TASK_HISTORY, because the task's overall state stayed 'started' and its schedule kept firing on time regardless of the refresh failing every single run. Full timeline: CLAUDE.md's 'SNOWFLAKE_RUN_MANIFEST_TASK / silver-loader OPERATE+SELECT gap' 5-whys section." \
    "{ printf '%s\n' \"SET database_name = '${db_name}';\" \"SET silver_schema_name = 'EDGARTOOLS_SILVER';\" \"SET loader_role_name = 'EDGARTOOLS_${ENV_UPPER}_LOADER';\"
cat infra/snowflake/sql/bootstrap/18_silver_loader_read_grants.sql; } | snow sql --connection ${SNOW_CONNECTION} -i"

  add_stage \
    "Snowflake: Streamlit dashboard" \
    "Uploads the Streamlit dashboard artifacts to the Snowflake dashboard stage." \
    "SNOW_CONNECTION=${snow_q} DASHBOARD_DATABASE=${db_name} bash infra/snowflake/streamlit/deploy.sh"

  # Source data work stays disabled until its Rules/feed baseline qualifies.
  add_stage \
    "MDM: clean migration and connectivity" \
    "Checks MDM connectivity and applies clean migrations. Source feeds remain disabled until configured Rules and Bookkeeping qualification." \
    "uv run --extra s3 --extra mdm-runtime edgar-warehouse mdm check-connectivity
uv run --extra s3 --extra mdm-runtime edgar-warehouse mdm migrate"


}

print_command_block() {
  local command_block="$1"
  local line
  while IFS= read -r line; do
    printf '    [preview only] %s\n' "$line"
  done <<< "$command_block"
}

print_plan() {
  local i
  build_stages
  echo "Ordered install plan for ${ENVIRONMENT}:"
  for i in "${!STAGE_NAMES[@]}"; do
    printf '\n%d. %s\n' "$((i + 1))" "${STAGE_NAMES[$i]}"
    printf '   %s\n' "${STAGE_DESCRIPTIONS[$i]}"
    print_command_block "${STAGE_COMMANDS[$i]}"
  done
  echo
  echo "Current install notes and issues:"
  known_install_notes_markdown | sed 's/^/  /'
}

record_event() {
  local stage="$1" status="$2" detail="$3"
  printf '%s\t%s\t%s\n' "$stage" "$status" "$detail" >> "$EVENTS_FILE"
}

write_state() {
  ensure_workspace
  INSTALL_ENVIRONMENT="$ENVIRONMENT" \
  INSTALL_AWS_PROFILE="$AWS_PROFILE_NAME" \
  INSTALL_DEPLOYER_PROFILE="$DEPLOYER_PROFILE" \
  INSTALL_AWS_REGION="$AWS_REGION_NAME" \
  INSTALL_SNOW_CONNECTION="$SNOW_CONNECTION" \
  INSTALL_MODE="$COMMAND" \
  python3 - "$STATE_FILE" "$EVENTS_FILE" <<'PY'
import datetime as _dt
import json
import os
import pathlib
import sys

state_path = pathlib.Path(sys.argv[1])
events_path = pathlib.Path(sys.argv[2])
events = []
if events_path.exists():
    for line in events_path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            events.append({"stage": parts[0], "status": parts[1], "detail": parts[2]})
state = {
    "updated_at": _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "environment": os.environ["INSTALL_ENVIRONMENT"],
    "aws_profile": os.environ["INSTALL_AWS_PROFILE"],
    "aws_deployer_profile": os.environ["INSTALL_DEPLOYER_PROFILE"],
    "aws_region": os.environ["INSTALL_AWS_REGION"],
    "snowflake_connection": os.environ["INSTALL_SNOW_CONNECTION"],
    "last_command": os.environ["INSTALL_MODE"],
    "events": events,
}
state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

execute_stage() {
  local command_block="$1"
  (
    set -o pipefail
    cd "$REPO_ROOT" && bash -c "set -euo pipefail
${command_block}" 2>&1 | redact_text
  )
}

run_doctor() {
  run_checks
  print_checks
  [[ "$CHECK_FAILURES" -eq 0 ]]
}

run_init() {
  : > "$EVENTS_FILE"
  ensure_workspace
  copy_templates_to_workspace
  record_event "init" "completed" "created ignored wizard workspace and copied example templates"
  write_state
  echo "Initialized ignored install workspace: ${WORKSPACE}"
}

run_deploy() {
  local i stage
  : > "$EVENTS_FILE"
  echo "Deploy starts with the same preview used by plan."
  print_plan
  if [[ "$APPLY" != "true" ]]; then
    build_stages
    for i in "${!STAGE_NAMES[@]}"; do
      record_event "${STAGE_NAMES[$i]}" "previewed" "deploy command ran without --apply"
    done
    write_state
    echo
    echo "Preview complete. No real commands were run because --apply was not provided."
    return 0
  fi

  require_expected_aws_target

  build_stages
  for i in "${!STAGE_NAMES[@]}"; do
    stage="${STAGE_NAMES[$i]}"
    echo
    echo "Apply stage: ${stage}"
    print_command_block "${STAGE_COMMANDS[$i]}"
    if confirm "Run this state-changing stage now?"; then
      if execute_stage "${STAGE_COMMANDS[$i]}"; then
        record_event "$stage" "applied" "operator confirmed and command completed"
      else
        record_event "$stage" "failed" "command failed; inspect terminal output and rerun after remediation"
        write_state
        return 1
      fi
    else
      record_event "$stage" "skipped" "operator declined apply confirmation"
      echo "Skipped stage: ${stage}"
    fi
  done
  write_state
  echo "Deploy command finished. See ${STATE_FILE#${REPO_ROOT}/} for recorded stage outcomes."
}

state_skipped_markdown() {
  if [[ ! -f "$STATE_FILE" ]]; then
    echo "- None recorded."
    return 0
  fi
  python3 - "$STATE_FILE" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
try:
    state = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("- Unable to read state.json.")
    raise SystemExit(0)
events = [event for event in state.get("events", []) if event.get("status") == "skipped"]
if not events:
    print("- None recorded.")
else:
    for event in events:
        stage = event.get("stage", "unknown stage")
        detail = event.get("detail", "")
        print(f"- {stage}: {detail}")
PY
}

generate_report() {
  local i line
  echo "# EdgarTools Install Report"
  echo
  echo "Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo
  echo "## Configuration"
  echo "- Environment: ${ENVIRONMENT}"
  echo "- AWS profile: ${AWS_PROFILE_NAME}"
  echo "- AWS deployer profile: ${DEPLOYER_PROFILE}"
  echo "- AWS region: ${AWS_REGION_NAME}"
  echo "- Snowflake connection: ${SNOW_CONNECTION}"
  echo "- Safety mode: preview-first; apply requires per-stage confirmation"
  echo
  echo "## Checks"
  for i in "${!CHECK_NAMES[@]}"; do
    printf -- '- %s: %s - %s\n' "${CHECK_NAMES[$i]}" "${CHECK_STATUSES[$i]}" "${CHECK_DETAILS[$i]}"
  done
  echo
  echo "## Planned Commands"
  build_stages
  for i in "${!STAGE_NAMES[@]}"; do
    printf '\n### %d. %s\n' "$((i + 1))" "${STAGE_NAMES[$i]}"
    printf '%s\n' "${STAGE_DESCRIPTIONS[$i]}"
    while IFS= read -r line; do
      printf -- '- preview only: `%s`\n' "$line"
    done <<< "${STAGE_COMMANDS[$i]}"
  done
  echo
  echo "## Skipped Stages"
  state_skipped_markdown
  echo
  echo "## Current Notes and Issues"
  known_install_notes_markdown
  echo
  echo "## Remediation"
  echo "- Run doctor until fail statuses are resolved."
  echo "- Create missing ignored Terraform backend and tfvars files from the templates staged under ${WORKSPACE}/setup/${ENVIRONMENT}/."
  echo "- WAREHOUSE_IMAGE_REF is auto-resolved from the ECR image publish stage's output file; only set it manually if that stage was skipped."
  echo "- Source/feed work remains disabled until its approved Rules version and verified baseline manifest qualify."
}

run_report() {
  local default_report raw_report
  ensure_workspace
  run_checks
  default_report="${WORKSPACE}/reports/install-${ENVIRONMENT}-$(date -u '+%Y%m%dT%H%M%SZ').md"
  REPORT_FILE="${REPORT_FILE:-$default_report}"
  mkdir -p "$(dirname "$REPORT_FILE")"
  raw_report="${TMPDIR:-/tmp}/install-report-$$.md"
  generate_report > "$raw_report"
  redact_text < "$raw_report" | tee "$REPORT_FILE"
  rm -f "$raw_report"
  echo
  echo "Wrote sanitized report: ${REPORT_FILE}"
}

dispatch_command() {
  case "$COMMAND" in
    doctor) run_doctor ;;
    init) run_init ;;
    plan) print_plan ;;
    deploy) run_deploy ;;
    report) run_report ;;
    *) fail "unsupported command after wizard selection: $COMMAND" ;;
  esac
}

refresh_config
if [[ "$COMMAND" == "wizard" ]]; then
  run_tui_wizard
fi

[[ "$EXPECTED_AWS_ACCOUNT_ID" =~ ^[0-9]{12}$ ]] || fail "--aws-account-id (or INSTALL_AWS_ACCOUNT_ID) must provide a 12-digit AWS account ID"

show_startup
confirm_environment
dispatch_command
