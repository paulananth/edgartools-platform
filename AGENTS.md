# EdgarTools Platform Agent Guide

## Current architecture

The executable CLI offers Rules, Bookkeeping, Change Journal, Clean MDM, and
Snowflake environment resolution. Inspect `edgar-warehouse --help` before
using a command from an older runbook. Acquisition and mastering are
configured in `rules/`; Bookkeeping owns work, leases, checkpoints and recovery;
Rules owns mappings and approvals; Change Journal owns durable delivery history.
Clean MDM owns identities, source readings, decisions and publication intents.

Keep hosted work AWS-focused: S3 bronze/warehouse storage, ECR images, and
Snowflake Postgres for MDM. Existing Snowflake SQL, dbt and dashboard assets
have their own callers and release checks. Verify live account and environment
state before deployment; a historical note is not an inventory.

For Company, Person, Relationship mastering, fresh local PostgreSQL 16
qualification, and database cleanup, read
[mastering operations](docs/agents/mastering-operations.md).

## Work ownership

- Never commit directly to `main`, including small fixes and documentation.
  Create a dedicated `<runtime>/<topic>` branch before the first edit.
- Use a dedicated git worktree for every active runtime session. Claude and
  Codex must not commit to the same branch or switch the shared checkout.
- Before editing or committing, inspect `git status --short`,
  `git branch --show-current`, `git log -1`, and `.planning/active-workstream`
  when present. Refresh the intended base against current upstream main.
- Treat current Codex work and other runtimes' edits as protected. Never
  overwrite, revert, stage or commit unrelated changes or rollback artifacts.
- If ticket work is found on main, preserve it on an owned branch immediately;
  restore main to origin/main only after protecting all shared work.
- If a branch changes unexpectedly, inspect its reflog and verify your own
  commits and stashes before recovery. If an unexpected other runtime commit
  appears before committing, stop and ask for ownership.
- Use `.planning/workstreams/<name>/` for your own workstream. Coordinate
  overlapping source, Terraform, generated JSON and planning changes first.

## Task checklists (every ticket, every runtime)

Every ticket file must keep all its parts as a Markdown checklist until it
closes, including small tickets and last-step work.

- Enumerate every part before starting: `- [ ] <part>`. Add newly found parts.
- Check a part only after completion and verification: `- [x] <part>`.
  Name the verification and stamp local ET on that same line, for example
  `2026-10-01 14:05 ET`.
- Keep skipped or moved parts: `- [ ] ~~<part>~~ deferred to <ticket>: <why>`.
  Never delete them from the checklist.
- Re-read the checklist before reporting completion. Any unchecked part means
  the task is incomplete; name what remains.
- Announce long scans, suites and deployments up front. Report elapsed time
  for any step exceeding ten minutes. Bound local test subprocesses to five
  minutes; a timeout leaves verification incomplete.

## Development and review

- Use `uv` for dependencies and Python execution. Use the extras the command
  needs; local mastering uses `uv sync --extra s3 --extra mdm`.
- Before changing code, use `gof-refactor-reviewer` on the relevant code and
  git history. Use `gof-pattern-selector` for a genuinely new design.
  Keep the existing design unless evidence justifies a refactor.
- Review Standards, Spec and GoF. Explicitly check the GoF skill's
  availability; if missing, state the limitation and review manually.
- When editing AGENTS.md or CLAUDE.md, use `writing-for-agents`. AGENTS.md is
  the shared instruction source; CLAUDE.md points here.
- Read large files in chunks. Keep acquisition source rules, domain merge
  rules and runtime capabilities separate.
- Read YAML through `edgar_warehouse.rules.files`. Preserve comments when
  editing an existing rule, then reload it to check values and digests.
- Record actual operator approvals with their exact words and tested evidence.
  Execution authorization is not a fabricated rule approval.
- Backfills must expose a bounded sample/limit. Test small before full runs.
- Use a file for multiline commit and PR messages (`git commit -F`,
  `gh pr create --body-file`), especially when they contain code spans.

## Verification

Run affected tests locally and preserve the full CI gate: unit, MDM,
architecture, PostgreSQL integration, and shell syntax checks. Retain Company
pagination, Rules authorization, Journal outage/recovery, lease fencing,
identity, publication and release security contracts.

PostgreSQL acceptance uses real PostgreSQL 16 migrations and restricted roles.
Missing prerequisites fail; mocks or skipped tests do not qualify a database.
Code, local qualification, hosted deployment and physical output verification
are separate claims. Record each accurately.

## Docker on macOS

Use Colima for local Docker work. Linux/CI builds use docker buildx and registry
cache. After local builds, inspect `docker system df -v` and clear unused build
cache with `docker builder prune` while Colima is running. Reclaim guest free
space with `colima ssh -- sudo fstrim -a`, comparing
`du -h ~/.colima/_lima/_disks/colima/datadisk` and `df -h` before and after.
`colima prune` clears downloaded assets. Preserve volumes and VM data unless
their exact removal is authorized; routine cleanup must not use
`docker system prune -a --volumes` or delete VM disk files. Report unavailable
Colima or Docker access.

## Hosted operations and safety

- Verify AWS account, profile, region, exact resource and current users before
  mutations. Keep secret values, credentials, live tfvars/state and sensitive
  generated application JSON out of commits and tool output.
- Passive AWS Terraform creates infrastructure shells and empty secret
  containers. It must not create runnable ECS task definitions, workflows,
  schedules, workload commands, image rollouts or runtime secret values.
- Use the admin profile for provisioning/access and `sec_platform_deployer`
  for application rollout. Runtime roles are service-assumed; create no
  runner access keys. Preserve scoped IAM and S3/versioning/encryption/public
  access protections.
- Publish images with `infra/scripts/publish-warehouse-image.sh`. The retired
  `deploy-aws-application.sh` is not an executable deployment route.
- Protect production bronze. A destructive database/storage cleanup requires
  exact targets, current no-use evidence and a reviewed recovery plan.
- Captured SEC artifacts remain immutable. Loaders skip captured/loaded files
  by default; operator repair uses explicit force. Keep SEC identity/rate
  controls. Data Onboarding uses captured artifacts, not new SEC requests.
- For hosted MDM connection/cutover work, read
  `docs/aws-mdm-snowflake-postgres-cutover.md`, verifying every command and
  schema against current code before execution. Clean MDM uses schema `mdm`.
- For Snowflake provisioning, read `infra/scripts/deploy-snowflake-stack.sh`
  and the chosen Terraform root. Confirm the connection, privileges and live
  target exist before using dev/prod examples. Use `uv run --with dbt-snowflake`
  for dbt. Never infer deployed gold or dashboard state from files alone.
