# EdgarTools Platform Agent Guide

## Scope

This repository is the data platform for SEC EDGAR and other provider data: a Rust source engine reads
captured files, MDM (PostgreSQL) masters them, silver lands them and Snowflake serves gold (operator,
2026-10-14: "Snowflake is still the target platform"). See CONTEXT.md for the words.

## Shared rules

**Read [CLAUDE.md](CLAUDE.md) first: it holds the rules every runtime follows** (parallel work and
branches, shared local data, path ownership and the overlap guard, task checklists). They are not
copied here, because copies drift (ticket 63). The sections below add what is Codex's and Grok's own, or
what CLAUDE.md links to.

## How to work in this repo (every runtime)

Learned the hard way; each is a standing operator rule.

**Tests and CI**
- Locally, run only the tests a change can affect, with `pytest --testmon`
  (`TESTMON_DATAFILE=~/.cache/edgartools/testmondata uv run pytest --testmon
  <folders>`; never with `-p no:cacheprovider`). After a change to a
  `.sql`, `.yaml` or data file, also run that area's test files by name. No
  local test run may take more than five minutes; CI runs everything.
- A change to skills, tickets or docs only needs no project environment: never
  `uv sync` a new worktree for it. Run the genericity lint, which reads files
  only: `uv run --no-project --with pytest -- pytest -q -p no:cacheprovider
  tests/unit/test_profiling_genericity.py` (under 1 s), and
  `tests/unit/test_guides_name_existing_paths.py` after a guide edit.
- Merge when every CI check is green and the PR is ready.
- A test states its expected answer; it never compares with a frozen copy of
  retired code. To retire such an oracle, write its answers into the test (or an
  answer file written once while the two still agree), change each answer once
  to see the test fail, and compute any value that follows the clock (ticket 88).
- A conclusion reached by reading code is not proof of behaviour: test each
  case the claim covers (one test per kind, per source), since the untested
  case is where a gap hides.
- Every background watcher (CI, a long test, a proof) has a deadline and an
  exit for every outcome, including the PR merging or closing. Stop test
  containers when a run ends, however it ends.
- A run already going (a proof, a load, a recovery) is checked every 30
  minutes, not on a tighter loop (operator, 2026-10-24: "do not use token
  constantly polling the runs check every 30 min"). A check that finds
  nothing changed sends no message. A failure, a finished part, or the end
  is reported at that check.
- Choose the cheapest proof that proves the change (the `mdm-engineering`
  skill, "Choose the cheapest proof"); say the time of any step over ten
  minutes before starting it.

**Commits, PRs and secrets**
- One branch per ticket, cut fresh off `origin/main` in its own worktree;
  never continue a ticket on a used or merged branch (PRs are squash-merged).
  Name it new: the remote keeps a merged branch's name and refuses a push to it
  (ticket 175's second PR). A fresh worktree's `.venv` folder exists before
  `uv sync` has run: test for `.venv/bin/pytest`, not the folder, before
  `uv run --no-sync`.
- Publish committed task changes, including operational and CI records, in a
  PR before ending the handoff. Keep the PR in draft while its declared change
  or validation is unfinished, then mark it ready after the final head passes.
  Report its URL and checked head. If the original PR already merged, publish
  residual notes from a fresh closeout branch; a local or pushed commit alone
  does not complete the review handoff. Preserve unfinished work explicitly.
- Work only in this repository. Never commit, push or open a PR in another
  repository, even for a task that spans repositories.
- Write commit messages and PR bodies to a file and pass them with
  `git commit -F` and `gh pr create --body-file`; inline text with backticks
  gets mangled.
- Never print a secret, a password, a token or a database address, and never
  ask the operator to type one into the chat. Read them from environment
  variables; if one is missing, ask the operator to set it in their own
  terminal. Redact by key name (any key containing `password`, `secret`,
  `token`, `key`, `dsn` or `url`), never by an exact list, and never pipe a
  secrets fetch to `head`, `cat` or a variable you print.
- This repository is public: counts and invented examples only, never a
  value from the data (a name, an identifier, a record).
- No request to a data provider (its site, API or documentation) without the
  operator's permission for that request.

**Talking with the operator**
- Every time shown to the operator is local ET, including times read from
  AWS, Postgres or CI, which report UTC.
- Report findings with their numbers and what they mean, not the steps you
  are about to take.
- Use the business words of `CONTEXT.md`; translate engine terms first (a
  "matching rule", not a "binding rule").
- Before asking for any approval, say in plain words what is approved, what
  it changes and on what evidence. A digest, hash or version number goes
  beside the explanation, never instead of it. A rule version has a
  descriptive name.
- Decide what follows from a ruling already given, say so, and go on. Stop
  only for an approval, a switch-on or a new kind of decision, and
  then ask one question at a time with your recommendation.

**Stores**
- Writes into Snowflake's SQL layer go through dbt. MDM's own Postgres store
  is written by its own code (SQLAlchemy), not dbt.

**Code and infrastructure**
- **Integer widths (operator, 2026-10-16):** use database `BIGINT` and
  64-bit `long`/`i64` for integer fields and counters, including years,
  quarters and positions. Never choose 32-bit `INT`/`INTEGER` or narrower
  integer types. Python's built-in integer has arbitrary precision: keep
  that source precision. Check representability before publication; preserve
  and flag an out-of-range original for explicit handling instead of wrapping,
  truncating, or converting it through floating point.
- **Number types (operator, 2026-11-04: "always use BIGINT and BIGDECIMAL and
  NUMBER"):** an integer is `BIGINT`; a decimal or fraction is an exact
  `BIGDECIMAL` in code and `NUMBER(precision, scale)` in a database, never
  `FLOAT`, `DOUBLE` or `REAL`. A number's precision and scale come from the
  profiled maximum digits and decimal places, with room for the widest value.
- A "same calendar day" check names its timezone, the business process's:
  `America/New_York` (through `pytz`; `zoneinfo` needs a tz database the
  images do not install).
- Provisioning that is not Terraform or a committed script does not survive an
  account rebuild, however well a runbook describes it. When one stage turns
  out to be an uncommitted manual step, assume every later stage in the same
  family is too.
- Before trusting a clean check, confirm the code under test is what is
  running: a check against stale, superseded infrastructure makes a false
  positive and a false negative look the same as success.
- Before running a multi-step workflow by hand, look for a machine already
  built for it (`aws stepfunctions list-state-machines`).

**Debugging**
- Before fixing an error, find its root cause (ask "why" until the answer is
  a cause, not a trigger) and fix that. Write a recurring lesson where it
  belongs: a skill, or this file.

## Tooling Rules

- Never use computer-use tools, browser automation or GUI interactions on this
  project (operator, 2026-10-30). Use service APIs and CLI tools, including for
  OpenMetadata publication, inspection, deletion and reset. Report a precise
  missing API/CLI capability instead of falling back to a UI.

- Use the GitHub CLI (`gh`) for GitHub pull requests, issues, reviews and CI operations.
- Before GitHub work, check `command -v gh`, `gh --version` and `gh auth status --hostname github.com`. Diagnose and repair executable, PATH, authentication or network failures. Report the exact failing command and error if `gh` remains blocked before using a fallback; attribute a failure to the sandbox only when the error establishes that cause.
- Use `uv` for Python dependency management and Python command execution.
- Do not use bare `pip` for repo workflows. Use `uv sync`, `uv pip install` for deliberate one-off installs, or `uv run --with <package>` for transient tools.
- Prefer `uv run --with dbt-snowflake dbt ...` over bare `dbt`.
- Project dependency source is PyPI. Declare only the libraries the code imports; `edgartools` is not a dependency (operator, 2026-10-28: "Remove it entirely").
- Docker images use AWS ECR for deployable artifacts.
- Use the Docker context already configured on the machine. Leave `DOCKER_HOST` unset. Publish images with `docker build` and `docker push` through `infra/scripts/publish-warehouse-image.sh --mode docker`.
- After a local image build, inspect `docker system df` and clear unused build cache with `docker builder prune`. Keep named volumes unless the operator names a volume to remove. If `docker info` cannot reach the daemon, report that blocker.

## GoF Design Review

- Before writing or modifying code, use the `gof-refactor-reviewer` skill to review the relevant existing code and its git history for evidence-backed Gang of Four refactoring opportunities. If the work is a new design with no existing code to review, use `gof-pattern-selector` instead.
- During code review, explicitly check whether `gof-refactor-reviewer` is available. When available, invoke it as part of the review; when unavailable, state that limitation and perform a focused manual design-pattern review.
- Every code review runs three axes, each reported under its own heading: **Standards** (this repo's rules), **Spec** (the ticket and the operator's words) and **GoF** (the `gof-refactor-reviewer` method on the same diff).
- The consult before code does not replace the review after it: a consult can bless a design while the diff still gets a load-bearing detail wrong.
- Do not force a design pattern into the code. Follow the skill's default of leaving the current design in place unless demonstrated change history and present-day costs justify the refactor.

Common setup:

```bash
uv sync --extra s3 --extra snowflake

# MDM runtime/dev work when needed:
uv sync --extra s3 --extra mdm-runtime
```

## Data And Parser Notes

- Raw provider download (capture) and bronze persistence are implemented by this repo, not by `edgartools`: a capture is a Bookkeeping worker (`edgar_warehouse/workers/provider_capture.py`).
- Every feed is read by the source engine from its rules (`rules/sources/<source>/`), with zero provider requests at read time; the old per-form parsers are deleted. The data skills (`skills/data-platform/`, `skills/data-onboarding/`) hold the how-to.
- SEC filing artifacts are additive and immutable after capture.
- Processing follows the source-coverage and Change Journal policy under
  "Shared local data"; retain immutable captures for verification and replay.

## Tests And Verification

Locally, run the affected tests ("How to work in this repo", above); CI runs
every folder below on each PR:

```bash
uv run pytest tests/unit tests/architecture
uv run pytest tests/mdm
```

Validation checks after deploy:

```bash
edgar-warehouse --help
python -c "from edgar_warehouse.cli import main; print('OK')"
uv run --with dbt-snowflake dbt test --target prod
```

Snowflake status query:

```sql
SELECT *
FROM EDGARTOOLS_PROD.EDGARTOOLS_GOLD.EDGARTOOLS_GOLD_STATUS
LIMIT 10;
```

## Safety Rules

- Do not commit local secrets, `.tfvars` with live values, generated Terraform state, or application JSON containing sensitive values.
- Do not put image digests, workflow rollout, schedules, or EDGAR identity values into AWS Terraform inputs.
- Do not change the ownership parser's `edgartools` imports without checking the `edgartools` changelog:

```python
from edgar.display.formatting import reverse_name
from edgar.entity.constants import _classify_is_individual
```

- Do not broaden IAM policies casually. Keep runner roles service-assumed and scoped.
- Do not remove S3 object/versioning/encryption/public-access protections.
- Do not destroy prod bronze storage without an explicit operator request and a reviewed migration plan.
- Preserve loader idempotency when reprocessing a full source delivery.

## Reference pages (moved out of this file, ticket 63)

- [AWS: Terraform, principals, infra flow, image publish, MDM, runtime settings](docs/agents/aws.md)
- [Snowflake native S3 pull, dbt and the dashboard](docs/agents/snowflake.md)
- [High-value files](docs/agents/architecture.md)
