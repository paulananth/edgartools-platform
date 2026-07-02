#!/usr/bin/env bash
set -u

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
RUN_DOCTOR=false
RUN_INSTALL=false
RUN_SYNC=false
RUN_CLOUD=false

show_usage() {
  printf '%s\n' \
    'Usage: bash scripts/setup-local-dev.sh [--doctor] [--install] [--sync-project] [--check-cloud]' \
    '' \
    'Diagnose local EdgarTools Platform development prerequisites by default.' \
    '' \
    'Options:' \
    '  --doctor        Run local software diagnostics (default when no options are provided)' \
    '  --install       Attempt guided local software installation, then run diagnostics' \
    '  --sync-project  Run uv sync --extra s3 --extra snowflake' \
    '  --check-cloud   Run optional AWS and Snowflake CLI configuration checks' \
    '  --help          Show this help'
}

print_section() {
  printf '\n%s\n' "$1"
  printf '%s\n' '------------------------'
}

pass_check() {
  PASS_COUNT=$((PASS_COUNT + 1))
  printf '[PASS] %s\n' "$1"
}

warn_check() {
  WARN_COUNT=$((WARN_COUNT + 1))
  printf '[WARN] %s\n' "$1"
  if [ "${2:-}" != "" ]; then
    printf '       Fix: %s\n' "$2"
  fi
}

fail_check() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  printf '[FAIL] %s\n' "$1"
  if [ "${2:-}" != "" ]; then
    printf '       Fix: %s\n' "$2"
  fi
}

print_summary() {
  printf '\nSummary: %s pass, %s warn, %s fail\n' "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT"
}

detect_platform() {
  if [ -n "${SETUP_LOCAL_DEV_PLATFORM:-}" ]; then
    printf '%s\n' "$SETUP_LOCAL_DEV_PLATFORM"
    return 0
  fi

  local kernel
  kernel="$(uname -s 2>/dev/null || printf 'unknown')"
  case "$kernel" in
    MINGW*|MSYS*|CYGWIN*) printf 'windows\n' ;;
    Darwin*) printf 'macos\n' ;;
    Linux*)
      if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
        printf 'wsl\n'
      else
        printf 'linux\n'
      fi
      ;;
    *) printf 'unknown\n' ;;
  esac
}

package_manager_hint() {
  case "$(detect_platform)" in
    windows) printf 'winget' ;;
    macos) printf 'brew' ;;
    linux|wsl) printf 'apt, dnf, or yum' ;;
    *) printf 'the platform package manager' ;;
  esac
}

install_hint() {
  local tool="$1"
  case "$tool" in
    bash)
      case "$(detect_platform)" in
        windows) printf 'Install Git Bash with winget install --id Git.Git --exact.' ;;
        macos) printf 'Install Bash with brew install bash.' ;;
        *) printf 'Install Bash with apt, dnf, or yum.' ;;
      esac
      ;;
    git)
      printf 'Install Git with %s.' "$(package_manager_hint)"
      ;;
    python)
      printf 'Install Python 3.12 or later with %s.' "$(package_manager_hint)"
      ;;
    uv)
      case "$(detect_platform)" in
        windows) printf 'Install uv with winget install --id astral-sh.uv --exact.' ;;
        macos) printf 'Install uv with brew install uv.' ;;
        *) printf 'Install uv from Astral or a trusted package source, then rerun this script.' ;;
      esac
      ;;
    gh)
      printf 'Install GitHub CLI (gh) with %s.' "$(package_manager_hint)"
      ;;
    aws)
      case "$(detect_platform)" in
        windows) printf 'Install AWS CLI v2 with winget install --id Amazon.AWSCLI --exact.' ;;
        macos) printf 'Install AWS CLI v2 with brew install awscli.' ;;
        *) printf 'Install AWS CLI v2 from the official AWS installer; distro awscli packages may be v1.' ;;
      esac
      ;;
    terraform)
      case "$(detect_platform)" in
        windows) printf 'Install Terraform 1.14.8 or later on the 1.14.x line with winget or HashiCorp releases; do not install 1.15.x for this repo.' ;;
        macos) printf 'Install Terraform 1.14.8 or later on the 1.14.x line with a pinned HashiCorp release or version manager; do not install 1.15.x for this repo.' ;;
        *) printf 'Install Terraform 1.14.8 or later on the 1.14.x line from HashiCorp releases; do not install 1.15.x for this repo.' ;;
      esac
      ;;
    snow)
      printf 'After uv is installed, run: uv tool install snowflake-cli.'
      ;;
    docker)
      case "$(detect_platform)" in
        windows) printf 'Install Docker Desktop with winget install --id Docker.DockerDesktop --exact, then start Docker Desktop.' ;;
        macos) printf 'Install Docker CLI and Colima with brew, then run infra/scripts/setup-colima.sh.' ;;
        *) printf 'Install Docker Engine using the guided Docker docs for your distro, then start the daemon.' ;;
      esac
      ;;
    docker-daemon)
      printf 'Start Docker Desktop, Colima, or the Docker service, then rerun this script.'
      ;;
    *)
      printf 'Install %s with %s.' "$tool" "$(package_manager_hint)"
      ;;
  esac
}

version_at_least() {
  local actual="$1"
  local minimum="$2"
  local actual_major actual_minor actual_patch min_major min_minor min_patch
  IFS=. read -r actual_major actual_minor actual_patch <<EOF_VERSION_ACTUAL
$actual
EOF_VERSION_ACTUAL
  IFS=. read -r min_major min_minor min_patch <<EOF_VERSION_MIN
$minimum
EOF_VERSION_MIN
  actual_patch="${actual_patch:-0}"
  min_patch="${min_patch:-0}"

  [[ "$actual_major" =~ ^[0-9]+$ ]] || return 1
  [[ "$actual_minor" =~ ^[0-9]+$ ]] || return 1
  [[ "$actual_patch" =~ ^[0-9]+$ ]] || return 1

  if (( actual_major > min_major )); then return 0; fi
  if (( actual_major < min_major )); then return 1; fi
  if (( actual_minor > min_minor )); then return 0; fi
  if (( actual_minor < min_minor )); then return 1; fi
  (( actual_patch >= min_patch ))
}

check_command() {
  local command_name="$1"
  local label="$2"
  local hint_key="$3"
  if command -v "$command_name" >/dev/null 2>&1; then
    pass_check "$label available"
    return 0
  fi
  fail_check "$label missing" "$(install_hint "$hint_key")"
  return 1
}

check_python() {
  local candidate version
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      version="$($candidate -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null || true)"
      if version_at_least "$version" "3.12.0"; then
        pass_check "Python $version available"
        return 0
      fi
      fail_check "Python $version found, but Python 3.12 or later is required" "$(install_hint python)"
      return 1
    fi
  done
  fail_check "Python missing" "$(install_hint python)"
  return 1
}

check_aws_cli() {
  if ! command -v aws >/dev/null 2>&1; then
    fail_check "AWS CLI missing" "$(install_hint aws)"
    return 1
  fi

  local version
  version="$(aws --version 2>&1 || true)"
  if [[ "$version" == aws-cli/2.* ]]; then
    pass_check "AWS CLI v2 available"
    return 0
  fi
  fail_check "AWS CLI v2 required; found: ${version:-unknown}" "$(install_hint aws)"
  return 1
}

check_terraform() {
  if ! command -v terraform >/dev/null 2>&1; then
    fail_check "Terraform missing" "$(install_hint terraform)"
    return 1
  fi

  local output first_line major minor patch
  output="$(terraform version 2>&1 || true)"
  first_line="${output%%$'\n'*}"
  if [[ "$first_line" =~ v([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
    major="${BASH_REMATCH[1]}"
    minor="${BASH_REMATCH[2]}"
    patch="${BASH_REMATCH[3]}"
    if [ "$major" = "1" ] && [ "$minor" = "14" ] && (( patch >= 8 )); then
      pass_check "Terraform $major.$minor.$patch compatible"
      return 0
    fi
  fi

  fail_check "Terraform 1.14.x is required, with patch 1.14.8 or later; found: ${first_line:-unknown}" "$(install_hint terraform)"
  return 1
}

check_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    fail_check "Docker CLI missing" "$(install_hint docker)"
    return 1
  fi
  pass_check "Docker CLI available"

  if docker info >/dev/null 2>&1; then
    pass_check "Docker daemon available"
    return 0
  fi
  fail_check "Docker daemon is not responding" "$(install_hint docker-daemon)"
  return 1
}

run_doctor() {
  print_section "Local Software Doctor"
  check_command bash "Bash" bash || true
  check_command git "Git" git || true
  check_python || true
  check_command uv "uv" uv || true
  check_command gh "GitHub CLI (gh)" gh || true
  check_aws_cli || true
  check_terraform || true
  check_command snow "Snowflake CLI (snow)" snow || true
  check_docker || true

  if [ -d .venv ]; then
    pass_check "Python virtual environment .venv exists"
  else
    warn_check "Python virtual environment .venv is missing" "Run: bash scripts/setup-local-dev.sh --sync-project"
  fi
}

run_logged() {
  printf 'Running: %s\n' "$*"
  "$@"
}

require_for_action() {
  local command_name="$1"
  local label="$2"
  local hint_key="$3"
  if command -v "$command_name" >/dev/null 2>&1; then
    return 0
  fi
  fail_check "$label missing" "$(install_hint "$hint_key")"
  return 1
}

run_sync_project() {
  print_section "Project Sync"
  if ! require_for_action uv "uv" uv; then
    return 1
  fi
  if run_logged uv sync --extra s3 --extra snowflake; then
    pass_check "Project dependencies synchronized with uv"
    return 0
  fi
  fail_check "uv sync failed" "Run the printed uv command again after fixing the reported dependency issue."
  return 1
}

run_cloud_checks() {
  print_section "Cloud Configuration Checks"
  local rc=0
  if require_for_action aws "AWS CLI" aws; then
    if run_logged aws sts get-caller-identity >/dev/null; then
      pass_check "AWS caller identity is available"
    else
      fail_check "AWS caller identity check failed" "Set AWS_PROFILE/AWS_DEFAULT_REGION or run aws configure/login for the intended account."
      rc=1
    fi
  else
    rc=1
  fi

  if require_for_action snow "Snowflake CLI (snow)" snow; then
    if run_logged snow connection list >/dev/null; then
      pass_check "Snowflake CLI connections are listable"
    else
      fail_check "Snowflake connection list failed" "Create or fix a Snowflake CLI connection; for dev DDL use SNOW_CONNECTION=snowconn."
      rc=1
    fi
    if [ -n "${SNOW_CONNECTION:-}" ]; then
      printf 'Selected Snowflake connection: %s\n' "$SNOW_CONNECTION"
    fi
  else
    rc=1
  fi
  return "$rc"
}

run_package_command() {
  printf 'Running: %s\n' "$*"
  if "$@"; then
    pass_check "Install command completed: $*"
    return 0
  fi
  warn_check "Install command failed: $*" "Review the package-manager output, refresh PATH or elevation, then rerun diagnostics."
  return 1
}

run_install() {
  print_section "Guided Install"
  local platform
  platform="$(detect_platform)"
  printf 'Platform: %s\n' "$platform"
  printf 'Installation is explicit; commands are printed before they run. Some tools may need a new shell, elevation, login, or reboot.\n'

  case "$platform" in
    windows)
      if command -v winget >/dev/null 2>&1; then
        run_package_command winget install --id Git.Git --exact --source winget --accept-package-agreements --accept-source-agreements || true
        run_package_command winget install --id GitHub.cli --exact --source winget --accept-package-agreements --accept-source-agreements || true
        run_package_command winget install --id Python.Python.3.12 --exact --source winget --accept-package-agreements --accept-source-agreements || true
        run_package_command winget install --id astral-sh.uv --exact --source winget --accept-package-agreements --accept-source-agreements || true
        run_package_command winget install --id Amazon.AWSCLI --exact --source winget --accept-package-agreements --accept-source-agreements || true
        run_package_command winget install --id Hashicorp.Terraform --version 1.14.9 --exact --source winget --accept-package-agreements --accept-source-agreements || true
        run_package_command winget install --id Docker.DockerDesktop --exact --source winget --accept-package-agreements --accept-source-agreements || true
      else
        warn_check "winget is unavailable" "Install winget or install the listed tools manually."
      fi
      ;;
    macos)
      if command -v brew >/dev/null 2>&1; then
        run_package_command brew install git gh python@3.12 uv awscli docker colima qemu || true
        warn_check "Terraform install remains pinned" "Install Terraform 1.14.8 or later on the 1.14.x line with a pinned release or version manager."
        if [ -x infra/scripts/setup-colima.sh ]; then
          run_package_command bash infra/scripts/setup-colima.sh || true
        else
          warn_check "Colima helper not found" "Run infra/scripts/setup-colima.sh after it is available."
        fi
      else
        warn_check "Homebrew is unavailable" "Install Homebrew, then rerun --install or install tools manually."
      fi
      ;;
    linux|wsl)
      if command -v apt-get >/dev/null 2>&1; then
        run_package_command sudo apt-get update || true
        run_package_command sudo apt-get install -y bash git gh python3 python3-venv docker.io || true
      elif command -v dnf >/dev/null 2>&1; then
        run_package_command sudo dnf install -y bash git gh python3 docker || true
      elif command -v yum >/dev/null 2>&1; then
        run_package_command sudo yum install -y bash git gh python3 docker || true
      else
        warn_check "No apt, dnf, or yum package manager found" "Install Bash, Git, GitHub CLI, Python 3.12, uv, AWS CLI v2, Terraform 1.14.x, Snowflake CLI, and Docker manually."
      fi
      warn_check "uv, AWS CLI v2, Terraform, and Docker may need guided install steps" "Use official installers for uv, AWS CLI v2, Terraform 1.14.x, and Docker Engine when distro packages are missing or outdated."
      ;;
    *)
      warn_check "Unknown platform" "Install the required tools manually, then rerun diagnostics."
      ;;
  esac

  if command -v uv >/dev/null 2>&1; then
    run_package_command uv tool install snowflake-cli || true
  else
    warn_check "Snowflake CLI install deferred" "Install uv first, then run: uv tool install snowflake-cli."
  fi
}

parse_args() {
  if [ "$#" -eq 0 ]; then
    RUN_DOCTOR=true
    return 0
  fi

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --doctor) RUN_DOCTOR=true ;;
      --install) RUN_INSTALL=true; RUN_DOCTOR=true ;;
      --sync-project) RUN_SYNC=true ;;
      --check-cloud) RUN_CLOUD=true ;;
      --help|-h) show_usage; exit 0 ;;
      *) show_usage; exit 2 ;;
    esac
    shift
  done
}

main() {
  parse_args "$@"

  if [ "$RUN_INSTALL" = true ]; then
    run_install || true
  fi
  if [ "$RUN_DOCTOR" = true ]; then
    run_doctor || true
  fi
  if [ "$RUN_SYNC" = true ]; then
    run_sync_project || true
  fi
  if [ "$RUN_CLOUD" = true ]; then
    run_cloud_checks || true
  fi

  print_summary
  if [ "$FAIL_COUNT" -gt 0 ]; then
    return 1
  fi
  return 0
}

main "$@"
