# Local Dev Setup Guided Installer Design

## Purpose

Create a platform-neutral Bash entry point for setting up local EdgarTools Platform development prerequisites without surprising the operator. The script will diagnose by default, install only when explicitly requested, and keep workstation tooling, Python project synchronization, and cloud configuration checks as separate actions.

The implementation must stay AWS-focused. It must not add or revive non-AWS deployment paths, registry targets, storage targets, workflow engines, or secret-management steps.

## Scope

Add `scripts/setup-local-dev.sh`.

The script supports:

- Windows through Git Bash as the primary Windows path.
- macOS through Homebrew and the existing Colima helper.
- Linux and WSL through Linux package-manager detection and guidance.
- Local software diagnostics by default.
- Guided installation through `--install`.
- Project environment synchronization through `--sync-project`.
- Optional cloud/configuration checks through `--check-cloud`.

The script does not:

- Print secrets.
- Require cloud credentials in default mode.
- Run Terraform, deploy infrastructure, create secrets, or start workloads.
- Install by default.
- Use bare `pip` for repo workflows.

## Claude/Codex Coordination

This repository may have active Claude and Codex workstreams at the same time. Codex setup work must not use, stage, commit, or push a Claude-owned branch or dirty worktree unless the user explicitly transfers ownership.

Before implementation, Codex should:

1. Fetch the current base branch:

   ```bash
   git fetch origin main
   ```

2. Inspect the Claude branch edit surface:

   ```bash
   git diff --name-only origin/main...<claude-branch>
   git status --short
   ```

3. Compare those paths to the intended Codex edit surface.

For this setup task, the intended Codex edit surface is limited to:

- `scripts/setup-local-dev.sh`.
- A focused setup-script test file.
- This setup design spec or a narrowly scoped setup documentation reference.

If the Claude branch touches any file Codex needs to edit, Codex must stop and ask for an ownership decision before modifying that file. This is especially important for Terraform roots, generated application JSON, broad existing test files, runtime source files, and `.planning/workstreams/**`.

The safest implementation path is a Codex-only branch or worktree from `origin/main`, for example:

```bash
git worktree add /tmp/edgartools-platform-codex-local-dev-setup \
  -b codex/local-dev-setup origin/main
```

Codex should stage and push only explicit setup-task files from that isolated workspace.

## Current Context

The repository documents these local prerequisites in `docs/runbook.md` and `AGENTS.md`:

- Bash.
- Git.
- Python 3.12 or later.
- `uv`.
- GitHub CLI `gh`.
- Docker tooling.
- AWS CLI v2.
- Terraform compatible with the repository's `1.14.x` requirement.
- Snowflake CLI `snow`.
- `dbt-snowflake` for dbt commands, run through `uv run --with dbt-snowflake`.

Windows deployment notes already prefer Git Bash for the image publish bridge. macOS Docker setup already has `infra/scripts/setup-colima.sh`; the new installer should reuse that script rather than duplicate Colima configuration.

## Design

### Commands

Default doctor:

```bash
bash scripts/setup-local-dev.sh
```

Equivalent explicit form:

```bash
bash scripts/setup-local-dev.sh --doctor
```

Optional actions:

```bash
bash scripts/setup-local-dev.sh --install
bash scripts/setup-local-dev.sh --sync-project
bash scripts/setup-local-dev.sh --check-cloud
```

Flags can be combined when their behavior is independent:

```bash
bash scripts/setup-local-dev.sh --install --sync-project
bash scripts/setup-local-dev.sh --doctor --check-cloud
```

### Platform Detection

Detect platform from `uname -s` and environment markers:

- `MINGW*`, `MSYS*`, `CYGWIN*`: Windows Git Bash.
- `Darwin*`: macOS.
- `Linux*` with `/proc/version` containing Microsoft or WSL markers: WSL/Linux.
- `Linux*`: Linux.

Windows Git Bash is the primary Windows target. WSL is treated as Linux unless a later operator workflow explicitly asks for Windows bridge behavior.

### Default Doctor

Default mode checks local software and prints pass, warn, or fail status with exact next actions.

Required checks:

- `bash` is available.
- `git` is available.
- Python command is available and version is `>=3.12`.
- `uv` is available.
- `gh` is available.
- `aws` is available and is AWS CLI v2.
- `terraform` is available and compatible with `1.14.x`.
- `snow` is available.
- `docker` is available.
- Docker daemon responds to `docker info`.
- `.venv` exists or the output suggests `--sync-project`.

Default doctor must not:

- Run `aws sts get-caller-identity`.
- Run Snowflake SQL.
- Read or print credential values.
- Install packages.

### Guided Install

`--install` attempts workstation tool installation only after explicit operator request.

The install flow remains guided:

- Print the command before running it.
- Use noninteractive package-manager flags only in `--install` mode.
- Continue to emit repair guidance if a package manager cannot install a tool.
- Explain when the operator may need a new shell, PATH refresh, elevation, login, or reboot.

Windows Git Bash:

- Prefer `winget` for native workstation tools.
- Install/check Git, GitHub CLI, AWS CLI v2, Docker Desktop, Terraform, and Python where package IDs are reliable.
- Do not install the latest Terraform blindly. Install a compatible `1.14.x` release only when the platform package source can pin it; otherwise print manual install guidance for the required line.
- Use `uv` for Python-managed tools where appropriate, including Snowflake CLI when native package-manager installation is not the best fit.
- Treat Docker Desktop as a guided install because it may require elevation, a service start, a reboot, or user login.

macOS:

- Prefer Homebrew.
- Install CLI tools through `brew`.
- For Docker, prefer Colima for this repository:
  - install `colima`, `docker`, and `qemu` through Homebrew when missing;
  - run or point to `infra/scripts/setup-colima.sh` for daemon configuration.

Linux and WSL:

- Detect `apt`, `dnf`, or `yum`.
- Install safer CLI tools where supported.
- Docker Engine install is guided and explicit because it may require sudo, repository configuration, system services, and group membership changes.

### Project Sync

`--sync-project` runs:

```bash
uv sync --extra s3 --extra snowflake
```

This is separate from workstation installation so an operator can diagnose tools without modifying the Python environment.

The script should fail clearly if `uv` is missing and suggest `--install`.

### Cloud and Configuration Checks

`--check-cloud` adds optional cloud/config checks:

- AWS identity check through `aws sts get-caller-identity`, respecting the caller's `AWS_PROFILE` and `AWS_DEFAULT_REGION`.
- Snowflake CLI connection listing through `snow connection list`.
- Optional selected Snowflake connection check when a connection flag or `SNOW_CONNECTION` is present.

Cloud checks must redact or avoid secret values. They should report account/user/connection availability only when those values are not sensitive.

### Output

Output should be concise and scan-friendly:

- One heading per section.
- One status line per check.
- Each failure includes a fix command or a short explanation.
- Final summary includes counts of pass, warn, and fail.
- Nonzero exit code when required local checks fail.

The script should avoid decorative Unicode so it remains readable in Git Bash, WSL, Linux terminals, macOS terminals, and CI logs.

## Error Handling

- Unknown flags print usage and exit `2`.
- Required local software failures exit `1` in doctor mode.
- Warnings do not fail the run.
- `--install` command failures report the failed command and continue when independent checks remain useful.
- `--sync-project` failure exits nonzero and points to the `uv` command that failed.
- Cloud check failures do not run by default; when requested, they are reported separately from local setup failures.

## Testing

Add focused shell-script tests with mocked commands and temporary PATH entries. The tests should not depend on real package managers, Docker, AWS, Snowflake, or network access.

Test cases:

- Default mode does not run install commands.
- Missing tool reports a clear failure and fix command.
- Python `3.12` or later passes; older versions fail.
- AWS CLI v2 passes; AWS CLI v1 fails.
- Terraform `1.14.x` passes; incompatible versions fail with a pinned-install fix.
- Docker CLI present but daemon unavailable reports a daemon-specific failure.
- `--sync-project` invokes `uv sync --extra s3 --extra snowflake`.
- `--check-cloud` invokes cloud checks only when requested.
- Windows Git Bash, macOS, Linux, and WSL platform detection branches select the expected guidance.

## Implementation Notes

Keep the script in Bash with small functions:

- `detect_platform`.
- `check_command`.
- `check_version`.
- `install_tool`.
- `run_doctor`.
- `run_install`.
- `run_sync_project`.
- `run_cloud_checks`.

Prefer structured case statements over long ad hoc conditionals. Keep platform-specific install commands in one section so future package ID updates are easy to review.

## Open Decisions

None. The user approved:

- Diagnose by default.
- Git Bash as the primary Windows target.
- Workstation setup and project sync both supported, but separate.
- Local software checks by default, cloud/config checks behind an explicit flag.
- Guided Installer Docker behavior.
