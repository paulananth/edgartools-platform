# Local Dev Setup Guided Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a platform-neutral Bash guided installer and doctor for local EdgarTools Platform development.

**Architecture:** Add one standalone Bash entry point that diagnoses by default, installs only with an explicit flag, and separates workstation checks from Python project sync and optional cloud checks. Add one focused stdlib `unittest` module that runs the script with mocked commands and temporary `PATH` entries so tests do not require package managers, Docker, AWS, Snowflake, or network access.

**Tech Stack:** Bash, Python stdlib `unittest`, subprocess tests with temporary executable mocks, existing `uv` workflow conventions.

---

## File Structure

- Create `scripts/setup-local-dev.sh`: Bash CLI for `--doctor`, `--install`, `--sync-project`, `--check-cloud`, and `--help`.
- Create `tests/unit/test_setup_local_dev_script.py`: isolated subprocess tests for the Bash script.
- Create `docs/superpowers/plans/2026-07-02-local-dev-setup-guided-installer.md`: this implementation plan.

## Task 1: Red Tests For Doctor Behavior

**Files:**
- Create: `tests/unit/test_setup_local_dev_script.py`
- Create later: `scripts/setup-local-dev.sh`

- [ ] **Step 1: Write tests that run `bash scripts/setup-local-dev.sh` through mocked commands.**

Tests must include:

```python
def test_default_mode_diagnoses_without_installing(self) -> None:
    with self.fake_tools() as ctx:
        ctx.add_standard_success_tools()
        ctx.add_tool('winget', 'log "$0 $*"')
        result = ctx.run_setup()
        self.assertEqual(result.returncode, 0, result.output)
        self.assertIn('Local Software Doctor', result.output)
        self.assertNotIn('winget', ctx.command_log())

def test_missing_required_tool_reports_failure_and_fix(self) -> None:
    with self.fake_tools() as ctx:
        ctx.add_standard_success_tools(omit={'gh'})
        result = ctx.run_setup()
        self.assertEqual(result.returncode, 1, result.output)
        self.assertIn('gh', result.output)
        self.assertIn('GitHub CLI', result.output)
```

- [ ] **Step 2: Run `python3 -m unittest tests.unit.test_setup_local_dev_script -q`.**

Expected result: fail because `scripts/setup-local-dev.sh` is missing.

## Task 2: Implement Minimal Doctor

**Files:**
- Create: `scripts/setup-local-dev.sh`
- Modify: `tests/unit/test_setup_local_dev_script.py`

- [ ] **Step 1: Add Bash argument parsing and summary counters.**

The script must default to doctor mode, reject unknown flags with exit code `2`, and print pass, warn, fail counts.

- [ ] **Step 2: Add checks for Bash, Git, Python, uv, gh, AWS CLI v2, Terraform 1.14.x, Snowflake CLI, Docker CLI, Docker daemon, and `.venv`.**

Python must be `>=3.12`; Terraform must be `1.14.x` and at least `1.14.8`; AWS must report `aws-cli/2.`.

- [ ] **Step 3: Run `python3 -m unittest tests.unit.test_setup_local_dev_script -q`.**

Expected result: doctor tests pass after implementation.

## Task 3: Add Version, Docker, Sync, Cloud, And Platform Tests

**Files:**
- Modify: `tests/unit/test_setup_local_dev_script.py`
- Modify: `scripts/setup-local-dev.sh`

- [ ] **Step 1: Add tests for Python 3.11 failure, AWS CLI v1 failure, Terraform 1.15 failure, and Docker daemon failure.**

Each test must assert exit code `1` and a specific repair message.

- [ ] **Step 2: Add tests for optional actions.**

`--sync-project` must log `uv sync --extra s3 --extra snowflake`. Default mode must not log `aws sts get-caller-identity` or `snow connection list`; `--check-cloud` must log both.

- [ ] **Step 3: Add tests for platform guidance.**

Use `SETUP_LOCAL_DEV_PLATFORM=windows|macos|linux|wsl` and missing `gh` to assert guidance mentions `winget`, `brew`, or `apt, dnf, or yum` as appropriate.

- [ ] **Step 4: Run tests and implement missing behavior until they pass.**

Run: `python3 -m unittest tests.unit.test_setup_local_dev_script -q`

Expected result: all focused setup-script tests pass.

## Task 4: Final Verification And Commit

**Files:**
- Verify: `scripts/setup-local-dev.sh`
- Verify: `tests/unit/test_setup_local_dev_script.py`
- Verify: `docs/superpowers/plans/2026-07-02-local-dev-setup-guided-installer.md`

- [ ] **Step 1: Run Bash syntax validation.**

Run: `bash -n scripts/setup-local-dev.sh`

Expected result: exit code `0`.

- [ ] **Step 2: Run focused unit tests.**

Run: `python3 -m unittest tests.unit.test_setup_local_dev_script -q`

Expected result: all setup tests pass.

- [ ] **Step 3: Run default doctor manually.**

Run: `bash scripts/setup-local-dev.sh`

Expected result: output contains local checks only; no cloud identity checks, no installs, no secrets.

- [ ] **Step 4: Inspect diff.**

Run: `git diff -- scripts/setup-local-dev.sh tests/unit/test_setup_local_dev_script.py docs/superpowers/plans/2026-07-02-local-dev-setup-guided-installer.md`

Expected result: only planned setup files changed.

- [ ] **Step 5: Commit and publish.**

Run:

```bash
git add scripts/setup-local-dev.sh tests/unit/test_setup_local_dev_script.py docs/superpowers/plans/2026-07-02-local-dev-setup-guided-installer.md
git commit -m "feat: add local dev setup doctor"
git push -u origin codex/local-dev-setup
```

## Self-Review

- Spec coverage: tasks cover default diagnosis, explicit install behavior, project sync, optional cloud checks, platform detection, Windows Git Bash guidance, macOS guidance, Linux and WSL guidance, safe output, and focused mocked tests.
- Placeholder scan: no deferred implementation placeholders remain; every task has exact paths and commands.
- Name consistency: planned Bash functions and test method names align with the implementation scope.
