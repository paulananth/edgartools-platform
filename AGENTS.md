# EdgarTools Platform Agent Guide (Codex and Grok)

**Read [CLAUDE.md](CLAUDE.md) first: it holds every rule shared by all runtimes**
(what the platform is, parallel work and branches, path ownership and the
overlap guard, task checklists, tests, merging, long runs, secrets, talking
with the operator, code and stores, code review, shared local data). No rule
is copied here, because copies drift (tickets 63 and 213). Where this file and
CLAUDE.md differ, CLAUDE.md rules. The sections below add only what Codex and
Grok need beyond it.

## Handoff

- Publish committed task changes, including operational and CI records, in a
  PR before ending the handoff. Keep the PR in draft while its declared change
  or validation is unfinished, then mark it ready after the final head passes.
  Report its URL and checked head. If the original PR already merged, publish
  residual notes from a fresh closeout branch; a local or pushed commit alone
  does not complete the review handoff. Preserve unfinished work explicitly.

## Tooling

- Use the GitHub CLI (`gh`) for GitHub pull requests, issues, reviews and CI operations.
- Before GitHub work, check `command -v gh`, `gh --version` and `gh auth status --hostname github.com`. Diagnose and repair executable, PATH, authentication or network failures. Report the exact failing command and error if `gh` remains blocked before using a fallback; attribute a failure to the sandbox only when the error establishes that cause.
- Use `uv` for Python dependency management and Python command execution: `uv sync`, `uv pip install` for deliberate one-off installs, or `uv run --with <package>` for transient tools, never bare `pip`.
- Common setup: `uv sync --extra s3 --extra mdm-runtime`.
- Project dependency source is PyPI. Declare only the libraries the code imports; `edgartools` is not a dependency (operator, 2026-10-28: "Remove it entirely").
- Docker images use AWS ECR for deployable artifacts. Use the Docker context already configured on the machine. Leave `DOCKER_HOST` unset. Publish images with `docker build` and `docker push` through `infra/scripts/publish-warehouse-image.sh --mode docker`.
- After a local image build, inspect `docker system df` and clear unused build cache with `docker builder prune`. Keep named volumes unless the operator names a volume to remove. If `docker info` cannot reach the daemon, report that blocker.
- OpenMetadata UI is permitted only for login and personal access token
  creation, using Playwright when the operator requests the UI or API/CLI
  cannot complete that operation. Restrict interaction to the configured
  instance and keep credentials and tokens out of output. Verify through
  API/CLI when available; all other project workflows remain API/CLI-only.

## GoF design review (beyond CLAUDE.md's "Code review")

- A new design with no existing code to review uses `gof-pattern-selector` in place of `gof-refactor-reviewer`.
- During code review, check whether `gof-refactor-reviewer` is available. When unavailable, state that limitation and perform a focused manual design-pattern review.
- Follow the skill's default of leaving the current design in place unless demonstrated change history and present-day costs justify the refactor.

## Data and parser notes

- Raw provider download (capture) and bronze persistence are implemented by this repo, not by `edgartools`: a capture is a Bookkeeping worker (`edgar_warehouse/workers/provider_capture.py`).
- Every feed is read by the source engine from its rules (`rules/sources/<source>/`), with zero provider requests at read time; the old per-form parsers are deleted. The data skills (`skills/data-platform/`, `skills/data-onboarding/`) hold the how-to.
- Retain immutable captures for verification and replay.

## Safety rules

- Do not commit local secrets, `.tfvars` with live values, generated Terraform state, or application JSON containing sensitive values.
- Do not put image digests, workflow rollout, schedules, or EDGAR identity values into AWS Terraform inputs.
- Do not broaden IAM policies casually. Keep runner roles service-assumed and scoped.
- Do not remove S3 object/versioning/encryption/public-access protections.
- Do not destroy prod bronze storage without an explicit operator request and a reviewed migration plan.
- Preserve loader idempotency when reprocessing a full source delivery.

## Reference pages

- [AWS: Terraform, principals, infra flow, image publish, MDM, runtime settings](docs/agents/aws.md)
- [High-value files](docs/agents/architecture.md)
- [Watching runs and choosing tests](docs/agents/watching-and-testing.md)
