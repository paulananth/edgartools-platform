#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  go-live.sh [wizard|doctor|init|plan|deploy|report] [options]

Commands:
  wizard   Interactive TUI wizard. This is the default when no command is provided.
  doctor   Run read-only local, AWS CLI, SnowCLI, Terraform, Docker, and config checks.
  init     Create only ignored local wizard state/templates under .edgartools-go-live/.
  plan     Print the ordered go-live plan and exact commands as preview-only.
  deploy   Preview the plan. Use --apply to enable per-stage confirmation and execution.
  report   Write and print a sanitized go-live report.

Options:
  --env <dev|prod>                Environment. Default: dev.
  --aws-profile <profile>         AWS admin/provisioning profile. Default: AWS_PROFILE or aws-admin-<env>.
  --deployer-profile <profile>    AWS application deployer profile. Default: sec_platform_deployer.
  --aws-region <region>           AWS region. Default: AWS_REGION, AWS_DEFAULT_REGION, or us-east-1.
  --snow-connection <name>        SnowCLI connection. Default: snowconn for dev, edgartools-prod for prod.
  --workspace <path>              Local ignored wizard workspace. Default: .edgartools-go-live.
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

ENVIRONMENT="dev"
AWS_PROFILE_NAME="${AWS_PROFILE:-}"
DEPLOYER_PROFILE="${GO_LIVE_DEPLOYER_PROFILE:-sec_platform_deployer}"
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
SNOW_CONNECTION=""
WORKSPACE=""
REPORT_FILE=""
APPLY=false
CANONICAL_PROD_AWS_ACCOUNT_ID="690839588395"
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
    --env) ENVIRONMENT="${2:?}"; shift 2 ;;
    --aws-profile) AWS_PROFILE_NAME="${2:?}"; shift 2 ;;
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

case "$ENVIRONMENT" in
  dev|prod) ;;
  *) fail "--env must be dev or prod" ;;
esac

if [[ "$APPLY" == "true" && "$COMMAND" != "deploy" && "$COMMAND" != "wizard" ]]; then
  fail "--apply is only valid with deploy or wizard"
fi

EVENTS_FILE="${TMPDIR:-/tmp}/go-live-events-$$.tsv"
trap 'rm -f "${EVENTS_FILE}"' EXIT

default_snow_connection_for_env() {
  case "$1" in
    dev) printf '%s\n' "snowconn" ;;
    prod) printf '%s\n' "edgartools-prod" ;;
    *) printf '%s\n' "edgartools-$1" ;;
  esac
}

refresh_config() {
  if [[ -z "$AWS_PROFILE_NAME" ]]; then
    AWS_PROFILE_NAME="aws-admin-${ENVIRONMENT}"
  fi
  if [[ -z "$SNOW_CONNECTION" ]]; then
    SNOW_CONNECTION="$(default_snow_connection_for_env "$ENVIRONMENT")"
  fi
  WORKSPACE="${WORKSPACE:-${REPO_ROOT}/.edgartools-go-live}"
  STATE_FILE="${WORKSPACE}/state.json"
  ENV_UPPER="$(printf '%s' "$ENVIRONMENT" | tr '[:lower:]' '[:upper:]')"
  RESOURCE_PREFIX="edgartools-${ENVIRONMENT}"
  SNOWFLAKE_DATABASE="EDGARTOOLS_${ENV_UPPER}"
}

selected_aws_account_id() {
  aws --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION_NAME" sts get-caller-identity --query Account --output text
}

require_canonical_prod_target() {
  local account_id
  [[ "$ENVIRONMENT" == "prod" ]] || return 0
  [[ "$AWS_REGION_NAME" == "us-east-1" ]] || fail "prod must target us-east-1"
  account_id="$(selected_aws_account_id 2>/dev/null)" || fail "unable to resolve AWS account for production profile ${AWS_PROFILE_NAME}"
  [[ "$account_id" == "$CANONICAL_PROD_AWS_ACCOUNT_ID" ]] || fail "production account mismatch: expected ${CANONICAL_PROD_AWS_ACCOUNT_ID}, got ${account_id}"
  [[ "$SNOWFLAKE_DATABASE" == "$CANONICAL_PROD_DATABASE" ]] || fail "production Snowflake target must be ${CANONICAL_PROD_DATABASE}"
}

use_gum() {
  [[ "${GO_LIVE_NO_GUM:-}" == "1" ]] && return 1
  command -v gum >/dev/null 2>&1 || return 1
  [[ "${GO_LIVE_FORCE_GUM:-}" == "1" ]] && return 0
  [[ -t 0 && -t 1 ]]
}

offer_gum_install() {
  [[ "${GO_LIVE_NO_GUM:-}" == "1" ]] && return 0
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
Go-live wizard
selected environment: ${ENVIRONMENT}
AWS profile: ${AWS_PROFILE_NAME}
AWS deployer profile: ${DEPLOYER_PROFILE}
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

  echo "EdgarTools go-live TUI"
  echo "Run with one command: bash infra/scripts/go-live.sh"
  echo "Default action is preview-only plan; deploy apply requires explicit selection and per-stage confirmations."
  echo

  selected="$(choose_one "Select operation" "plan" "doctor" "init" "plan" "deploy" "report")"
  COMMAND="$selected"

  old_env="$ENVIRONMENT"
  old_aws_default="aws-admin-${old_env}"
  old_snow_default="$(default_snow_connection_for_env "$old_env")"
  ENVIRONMENT="$(choose_one "Select environment" "$ENVIRONMENT" "dev" "prod")"
  if [[ "$AWS_PROFILE_NAME" == "$old_aws_default" ]]; then
    AWS_PROFILE_NAME="aws-admin-${ENVIRONMENT}"
  fi
  if [[ "$SNOW_CONNECTION" == "$old_snow_default" ]]; then
    SNOW_CONNECTION="$(default_snow_connection_for_env "$ENVIRONMENT")"
  fi
  refresh_config

  AWS_PROFILE_NAME="$(prompt_value "AWS admin/provisioning profile" "$AWS_PROFILE_NAME")"
  DEPLOYER_PROFILE="$(prompt_value "AWS application deployer profile" "$DEPLOYER_PROFILE")"
  AWS_REGION_NAME="$(prompt_value "AWS region" "$AWS_REGION_NAME")"
  SNOW_CONNECTION="$(prompt_value "Snowflake connection" "$SNOW_CONNECTION")"
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
    -e "s#([Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]|[Tt][Oo][Kk][Ee][Nn]|[Ss][Ee][Cc][Rr][Ee][Tt]|[Aa][Pp][Ii][_-]?[Kk][Ee][Yy])([=:][^[:space:]]+)#\1=<redacted>#g" \
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

known_go_live_notes_markdown() {
  cat <<'EOF'
- `bronze_seed_silver_gold` now needs the Step Functions `batch_size` input defaulted and stringified before ECS `ContainerOverrides.Command`; older deployed definitions can fail immediately in `SeedFromBronze`.
- Fresh silver stores may not contain the legacy `sec_tracked_universe` table; table-count reporting must treat that missing table as zero so `seed-bronze-batches` can finish after writing the CIK batch manifest.
- First-time copied-bronze loads may not have `warehouse/silver/sec/shard-manifest.json`; `bootstrap-batch` and `mdm run`'s silver reader both fall back to the monolith `silver.duckdb` when no shard manifest exists yet (write side: `warehouse_orchestrator.py`'s `shard_manifest_missing_monolith_fallback`; read side: `mdm/cli.py`'s `_silver_reader()`). Because all concurrent batches in this fallback mode write to the same single monolith file, `BatchSilver`'s `MaxConcurrency` is a write-race risk lever, not just a throughput one. `MaxConcurrency=2` was validated end-to-end in prod (run `bronze-seed-silver-gold-1782351277`, 2026-06-24/25: `SeedFromBronze` → `BatchSilver` (zero `sec_pull_started`) → `MdmRun` → `MdmBackfill` → `MdmSync` → `MdmVerify` → `GoldRefresh` all `SUCCEEDED`). Current source is `MaxConcurrency=4`, which is **unvalidated** -- watch the next live run closely for monolith write contention (DuckDB lock errors, partial/duplicate rows) before trusting it.
- `bootstrap-batch`'s idempotency check only consulted the silver checkpoint table, not S3 bronze existence directly -- on a fresh silver DB this caused real per-CIK SEC API calls during `BatchSilver` despite the bronze already existing in S3 (confirmed live: ~1 batch/hour with live `sec_pull_started` events). Fixed via a CIK-prefix glob fallback (`StorageLocation.find_existing`) and PR95's `merge_filings` bulk-upsert path. Always publish and deploy a fresh warehouse image that contains PR95 before using the one-click stage, and verify a `bronze_seed_silver_gold` run's first batch shows zero `sec_pull_started` events in CloudWatch within minutes of starting -- don't wait an hour to check.
- Do not treat `BatchSilver` succeeding as proof the whole chain works: the first time this chain ever reached `MdmRun` in prod, it failed separately (read-side shard-manifest-missing bug, distinct from the write-side bug above). Do not flip Blocker 4 / hosted graph E2E to PASS until `SeedFromBronze`, `BatchSilver`, `MdmRun`, `MdmBackfill`, `MdmSync`, `MdmVerify`, and `GoldRefresh` all succeed in prod and the run shows zero `sec_pull_started` events during `BatchSilver`.
- **Do not redrive a failed `bronze_seed_silver_gold` execution after deploying a fix.** AWS Step Functions pins a redriven execution to the exact task-definition revision that was active when that execution last reached the failed state -- it does NOT pick up newly deployed revisions. Confirmed live: redriving after deploying a fix still ran the OLD task-definition revision and reproduced the OLD failure. Always start a fresh execution to pick up a new image/fix; only redrive when no relevant image has changed since the failure (e.g. a transient network blip) and you want to skip re-running already-succeeded `BatchSilver` batches.
- `deploy-aws-application.sh --enable-mdm` silently defaults MDM task definitions to the *warehouse* image ref when `--mdm-image-ref` is omitted -- they need different images (MDM installs `.[s3,mdm-runtime]`, warehouse installs `.[s3]`). Always pass `--mdm-image-ref` explicitly; the go-live wizard's stages now do this automatically by publishing and resolving both image refs separately.
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
    if [[ "$ENVIRONMENT" == "prod" ]]; then
      account_id="$(selected_aws_account_id 2>/dev/null || true)"
      if [[ "$account_id" == "$CANONICAL_PROD_AWS_ACCOUNT_ID" ]]; then
        add_check "canonical prod account" "pass" "AWS caller matches the canonical production account"
      else
        add_check "canonical prod account" "fail" "production account mismatch; expected ${CANONICAL_PROD_AWS_ACCOUNT_ID}"
      fi
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

  # Phase 9 finding: infra/aws-<env>-application.json is generated, gitignored,
  # and never committed (D-10). It does not survive a fresh checkout/worktree
  # and is the AWS MDM E2E stage's hard precondition (run-aws-mdm-e2e.sh exits 1
  # before any Step Functions status call if it is missing). Surface its absence
  # here rather than letting that stage fail with a less obvious error.
  if [[ -f "${REPO_ROOT}/infra/aws-${ENVIRONMENT}-application.json" ]]; then
    add_check "prod application summary" "pass" "infra/aws-${ENVIRONMENT}-application.json present"
    local warehouse_bucket
    warehouse_bucket="$(application_manifest_value warehouse_bucket_name 2>/dev/null || true)"
    if [[ -z "$warehouse_bucket" ]]; then
      add_check "first-load shard manifest" "warn" "application summary does not expose warehouse_bucket_name; cannot verify silver shard manifest prerequisite"
    elif command -v aws >/dev/null 2>&1 && aws --profile "$DEPLOYER_PROFILE" --region "$AWS_REGION_NAME" s3api head-object --bucket "$warehouse_bucket" --key "warehouse/silver/sec/shard-manifest.json" >/dev/null 2>&1; then
      add_check "first-load shard manifest" "pass" "warehouse/silver/sec/shard-manifest.json exists in the selected warehouse bucket"
    else
      add_check "first-load shard manifest" "warn" "warehouse/silver/sec/shard-manifest.json is missing or not readable; bronze_seed_silver_gold will use sequential monolith fallback on first-time loads"
    fi
    if [[ "$ENVIRONMENT" == "prod" ]]; then
      for bucket in bronze_bucket_name warehouse_bucket_name snowflake_export_bucket_name; do
        expected_bucket="edgartools-prod-${bucket%_bucket_name}-690839588395"
        [[ "$bucket" == "snowflake_export_bucket_name" ]] && expected_bucket="edgartools-prod-snowflake-export-690839588395"
        if [[ "$(application_manifest_value "$bucket" 2>/dev/null || true)" == "$expected_bucket" ]]; then
          add_check "canonical ${bucket}" "pass" "manifest uses canonical production bucket"
        else
          add_check "canonical ${bucket}" "fail" "manifest does not use ${expected_bucket}"
        fi
      done
    fi
  else
    add_check "prod application summary" "warn" "infra/aws-${ENVIRONMENT}-application.json missing; regenerate via the 'AWS: ECS task definitions and Step Functions' stage before running the AWS MDM E2E stage"
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
  local aws_profile_q region_q deployer_q env_q snow_q image_tag db_name
  local mdm_instance_name mdm_network_policy_name mdm_network_rule_name mdm_schema_name
  local mdm_instance_name_q mdm_network_policy_name_q mdm_network_rule_name_q mdm_schema_name_q mdm_comment_env_q
  STAGE_NAMES=()
  STAGE_DESCRIPTIONS=()
  STAGE_COMMANDS=()
  aws_profile_q="$(shell_quote "$AWS_PROFILE_NAME")"
  region_q="$(shell_quote "$AWS_REGION_NAME")"
  deployer_q="$(shell_quote "$DEPLOYER_PROFILE")"
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

  add_stage \
    "AWS: Terraform state bucket" \
    "Remote state bootstrap for the AWS Terraform backend." \
    "cd infra/terraform/bootstrap-state
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform init
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform plan
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform apply"

  add_stage \
    "AWS: passive infrastructure" \
    "VPC, S3 bronze/warehouse/export buckets, S3 endpoint, ECR, ECS cluster, CloudWatch logs, SNS, KMS, and empty Secrets Manager containers." \
    "cd infra/terraform/accounts/${ENVIRONMENT}
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform init -backend-config=backend.hcl
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform plan
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform apply"

  add_stage \
    "AWS: access roles/policies" \
    "AWS access Terraform for deployer, runner execution/task roles, and scoped policies." \
    "cd infra/terraform/access/aws/accounts/${ENVIRONMENT}
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform init -backend-config=backend.hcl
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform plan
AWS_PROFILE=${aws_profile_q} AWS_DEFAULT_REGION=${region_q} terraform apply"

  add_stage \
    "AWS: ECR image publish" \
    "Publishes the warehouse AND MDM images to AWS ECR with dev and immutable rollback/audit tags. Writes both resolved digest-pinned image refs to local files so the next stage can pick them up automatically. Publishing both here (not just warehouse) is required: deploy-aws-application.sh silently defaults the MDM task definitions to the warehouse image ref when --mdm-image-ref is omitted, which is wrong (MDM has different runtime deps, .[s3,mdm-runtime] vs .[s3]) and was hit live in production on 2026-06-23." \
    "AWS_PROFILE=${deployer_q} bash infra/scripts/publish-warehouse-image.sh --aws-region ${AWS_REGION_NAME} --ecr-repository edgartools-${ENVIRONMENT}-warehouse --role warehouse --image-tag ${image_tag} --mode auto --cache-from-tag ${ENVIRONMENT} --also-tag ${ENVIRONMENT} --output-file infra/aws-${ENVIRONMENT}-warehouse-image-ref.txt
AWS_PROFILE=${deployer_q} bash infra/scripts/publish-warehouse-image.sh --aws-region ${AWS_REGION_NAME} --ecr-repository edgartools-${ENVIRONMENT}-mdm --role mdm --image-tag ${image_tag} --mode auto --cache-from-tag ${ENVIRONMENT} --also-tag ${ENVIRONMENT} --output-file infra/aws-${ENVIRONMENT}-mdm-image-ref.txt"

  add_stage \
    "AWS: ECS task definitions and Step Functions" \
    "Registers ECS task definitions (warehouse AND MDM), creates or updates all Step Functions including bronze_seed_silver_gold, and wires application CloudWatch logs from passive outputs. Auto-resolves both image refs from the ECR publish stage's output files; falls back to WAREHOUSE_IMAGE_REF/MDM_IMAGE_REF only if those files are missing (e.g. publish stage skipped). Always passes --mdm-image-ref explicitly and --enable-mdm so the MDM task definitions never silently fall back to the warehouse image." \
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
AWS_PROFILE=${deployer_q} bash infra/scripts/deploy-aws-application.sh --env ${ENVIRONMENT} --aws-profile ${DEPLOYER_PROFILE} --aws-region ${AWS_REGION_NAME} --skip-build --image-ref \"\${resolved_warehouse_image_ref}\" --mdm-image-ref \"\${resolved_mdm_image_ref}\" --enable-mdm --output-file infra/aws-${ENVIRONMENT}-application.json"

  add_stage \
    "Snowflake: native-pull foundation" \
    "baseline database/schemas/warehouses plus native-pull integration, stage, source tables, pipe, stream, procedures, task, and access grants." \
    "SNOW_CONNECTION=${snow_q} bash infra/scripts/deploy-snowflake-stack.sh --env ${ENVIRONMENT} --snow-connection ${SNOW_CONNECTION} --run-validation"

  add_stage \
    "Snowflake: dbt gold" \
    "Builds and tests dbt gold dynamic-table/view models in the Snowflake analytics target." \
    "cd infra/snowflake/dbt/edgartools_gold
uv run --with dbt-snowflake dbt deps
uv run --with dbt-snowflake dbt run --target ${ENVIRONMENT}
uv run --with dbt-snowflake dbt test --target ${ENVIRONMENT}"

  add_stage \
    "Snowflake: Streamlit dashboard" \
    "Uploads the Streamlit dashboard artifacts to the Snowflake dashboard stage." \
    "SNOW_CONNECTION=${snow_q} DASHBOARD_DATABASE=${db_name} bash infra/snowflake/streamlit/deploy.sh"

  add_stage \
    "Snowflake Postgres / graph prerequisites" \
    "Delegates Snowflake Postgres credential rotation, migration, and AWS secret bootstrap to the maintained bootstrap script, then grants the hosted graph app against the selected database." \
    "bash infra/scripts/bootstrap-prod-mdm.sh --env ${ENVIRONMENT} --snow-connection ${SNOW_CONNECTION} --instance-name ${mdm_instance_name_q} --aws-profile ${AWS_PROFILE_NAME} --aws-region ${AWS_REGION_NAME} --name-prefix edgartools-${ENVIRONMENT}
snow sql --connection ${SNOW_CONNECTION} --enable-templating JINJA --filename infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql -D database=${db_name}"

  add_stage \
    "AWS: bronze_seed_silver_gold (one-click data refresh)" \
    "Starts the bronze_seed_silver_gold Step Function, which discovers CIKs directly from existing S3 bronze (zero new SEC calls) and chains SeedFromBronze -> BatchSilver -> MdmRun -> MdmBackfill -> MdmSync -> MdmVerify -> GoldRefresh on ECS. Polls until the execution reaches a terminal state and fails this stage unless it reaches SUCCEEDED. This is the canonical one-click path for cold-starting or recovering an environment's silver/MDM/gold from a bronze snapshot that's already in S3 (e.g. synced in from another environment) -- see CLAUDE.md's phased pipeline table." \
    "account_id=\"\$(aws --profile ${deployer_q} sts get-caller-identity --query Account --output text)\"
state_machine_arn=\"arn:aws:states:${AWS_REGION_NAME}:\${account_id}:stateMachine:edgartools-${ENVIRONMENT}-bronze-seed-silver-gold\"
execution_name=\"bronze-seed-silver-gold-\$(date +%s)\"
execution_arn=\"\$(aws --profile ${deployer_q} --region ${AWS_REGION_NAME} stepfunctions start-execution --state-machine-arn \"\${state_machine_arn}\" --name \"\${execution_name}\" --input '{\"batch_size\": 100}' --query executionArn --output text)\"
echo \"Started execution: \${execution_arn}\"
echo \"This runs BatchSilver at maxConcurrency=4 against the monolith silver.duckdb fallback (no shard manifest yet) -- only maxConcurrency=2 has been validated end-to-end in prod, so watch closely for monolith write-contention errors on this run. With PR95's merge_filings bulk-upsert optimization in the deployed warehouse image, cached-bronze batches should be materially faster than the old per-row path. If progress looks like the old multi-minute-per-batch behavior, stop and verify the active task definition image was freshly published from a commit that contains PR95.\"
last_succeeded=-1
while true; do
  status=\"\$(aws --profile ${deployer_q} --region ${AWS_REGION_NAME} stepfunctions describe-execution --execution-arn \"\${execution_arn}\" --query status --output text)\"
  map_run_arn=\"\$(aws --profile ${deployer_q} --region ${AWS_REGION_NAME} stepfunctions list-map-runs --execution-arn \"\${execution_arn}\" --query 'mapRuns[0].mapRunArn' --output text 2>/dev/null)\"
  if [[ -n \"\${map_run_arn}\" && \"\${map_run_arn}\" != \"None\" ]]; then
    succeeded=\"\$(aws --profile ${deployer_q} --region ${AWS_REGION_NAME} stepfunctions describe-map-run --map-run-arn \"\${map_run_arn}\" --query executionCounts.succeeded --output text 2>/dev/null || echo -1)\"
    failed=\"\$(aws --profile ${deployer_q} --region ${AWS_REGION_NAME} stepfunctions describe-map-run --map-run-arn \"\${map_run_arn}\" --query executionCounts.failed --output text 2>/dev/null || echo 0)\"
    total=\"\$(aws --profile ${deployer_q} --region ${AWS_REGION_NAME} stepfunctions describe-map-run --map-run-arn \"\${map_run_arn}\" --query executionCounts.total --output text 2>/dev/null || echo '?')\"
    if [[ \"\${succeeded}\" != \"\${last_succeeded}\" ]]; then
      echo \"Status: \${status} -- BatchSilver \${succeeded}/\${total} succeeded, \${failed} failed\"
      last_succeeded=\"\${succeeded}\"
    fi
  else
    echo \"Status: \${status}\"
  fi
  case \"\${status}\" in
    SUCCEEDED) break ;;
    FAILED|ABORTED|TIMED_OUT)
      echo \"Execution did not succeed: \${status}. Inspect via: aws stepfunctions get-execution-history --execution-arn \${execution_arn}\" >&2
      echo \"If only BatchSilver succeeded and a later stage (MdmRun etc.) failed, and you intend to redeploy a fix before retrying: do NOT redrive this execution -- AWS Step Functions pins a redriven execution to the task-definition revision that was active when it last reached that state, not whatever you redeploy afterward. Start a fresh execution instead so it binds to the current state machine definition.\" >&2
      exit 1
      ;;
    *) sleep 60 ;;
  esac
done
echo \"bronze_seed_silver_gold SUCCEEDED. Do not treat this alone as Blocker 4 / hosted-graph-E2E PASS -- separately confirm via CloudWatch logs that zero sec_pull_started events occurred during BatchSilver.\""

  add_stage \
    "MDM + graph: connectivity, migrations, sync, verification" \
    "Runs bounded MDM connectivity, migrations, graph sync, and graph verification commands." \
    "uv run --extra s3 --extra mdm-runtime edgar-warehouse mdm check-connectivity
uv run --extra s3 --extra mdm-runtime edgar-warehouse mdm migrate
uv run --extra s3 --extra mdm-runtime edgar-warehouse mdm seed-universe --tracking-status bootstrap_pending
uv run --extra s3 --extra mdm-runtime edgar-warehouse mdm run --entity-type all --limit 100
uv run --extra s3 --extra mdm-runtime edgar-warehouse mdm sync-graph --limit 100
uv run --extra snowflake edgar-warehouse mdm verify-graph"

  add_stage \
    "MDM + graph: AWS MDM E2E/status checks" \
    "Checks Step Functions status and runs bounded AWS-only MDM E2E verification." \
    "bash infra/scripts/run-aws-mdm-e2e.sh --env ${ENVIRONMENT} --aws-profile ${DEPLOYER_PROFILE} --aws-region ${AWS_REGION_NAME} --status-only
bash infra/scripts/run-aws-mdm-e2e.sh --env ${ENVIRONMENT} --aws-profile ${DEPLOYER_PROFILE} --aws-region ${AWS_REGION_NAME} --mdm-run-limit 5 --graph-limit 100"

  add_stage \
    "Data: bounded smoke only" \
    "Runs bounded smoke commands only; unbounded bootstrap is not part of the default go-live path." \
    "EDGAR_IDENTITY=\"\${EDGAR_IDENTITY:?set EDGAR_IDENTITY with contact email}\" WAREHOUSE_ENVIRONMENT=${ENVIRONMENT} WAREHOUSE_RUNTIME_MODE=infrastructure_validation uv run --extra s3 edgar-warehouse seed-universe --limit 100
EDGAR_IDENTITY=\"\${EDGAR_IDENTITY:?set EDGAR_IDENTITY with contact email}\" WAREHOUSE_ENVIRONMENT=${ENVIRONMENT} WAREHOUSE_RUNTIME_MODE=infrastructure_validation uv run --extra s3 edgar-warehouse bootstrap-next --limit 100"
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
  echo "Ordered go-live plan for ${ENVIRONMENT}:"
  for i in "${!STAGE_NAMES[@]}"; do
    printf '\n%d. %s\n' "$((i + 1))" "${STAGE_NAMES[$i]}"
    printf '   %s\n' "${STAGE_DESCRIPTIONS[$i]}"
    print_command_block "${STAGE_COMMANDS[$i]}"
  done
  echo
  echo "Current go-live notes and issues:"
  known_go_live_notes_markdown | sed 's/^/  /'
}

record_event() {
  local stage="$1" status="$2" detail="$3"
  printf '%s\t%s\t%s\n' "$stage" "$status" "$detail" >> "$EVENTS_FILE"
}

write_state() {
  ensure_workspace
  GO_LIVE_ENVIRONMENT="$ENVIRONMENT" \
  GO_LIVE_AWS_PROFILE="$AWS_PROFILE_NAME" \
  GO_LIVE_DEPLOYER_PROFILE="$DEPLOYER_PROFILE" \
  GO_LIVE_AWS_REGION="$AWS_REGION_NAME" \
  GO_LIVE_SNOW_CONNECTION="$SNOW_CONNECTION" \
  GO_LIVE_MODE="$COMMAND" \
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
    "environment": os.environ["GO_LIVE_ENVIRONMENT"],
    "aws_profile": os.environ["GO_LIVE_AWS_PROFILE"],
    "aws_deployer_profile": os.environ["GO_LIVE_DEPLOYER_PROFILE"],
    "aws_region": os.environ["GO_LIVE_AWS_REGION"],
    "snowflake_connection": os.environ["GO_LIVE_SNOW_CONNECTION"],
    "last_command": os.environ["GO_LIVE_MODE"],
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
  echo "Initialized ignored go-live workspace: ${WORKSPACE}"
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

  require_canonical_prod_target

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
  echo "# EdgarTools Go-Live Report"
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
  known_go_live_notes_markdown
  echo
  echo "## Remediation"
  echo "- Run doctor until fail statuses are resolved."
  echo "- Create missing ignored Terraform backend and tfvars files from the templates staged under ${WORKSPACE}/setup/${ENVIRONMENT}/."
  echo "- WAREHOUSE_IMAGE_REF is auto-resolved from the ECR image publish stage's output file; only set it manually if that stage was skipped."
  echo "- For first-time copied-bronze loads, expect bronze_seed_silver_gold BatchSilver to run sequentially through monolith fallback until silver shard metadata is published."
  echo "- Keep data smoke bounded; do not run unbounded bootstrap from the wizard default path."
}

run_report() {
  local default_report raw_report
  ensure_workspace
  run_checks
  default_report="${WORKSPACE}/reports/go-live-${ENVIRONMENT}-$(date -u '+%Y%m%dT%H%M%SZ').md"
  REPORT_FILE="${REPORT_FILE:-$default_report}"
  mkdir -p "$(dirname "$REPORT_FILE")"
  raw_report="${TMPDIR:-/tmp}/go-live-report-$$.md"
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

show_startup
confirm_environment
dispatch_command
