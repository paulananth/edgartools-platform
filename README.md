# EdgarTools Platform

A configuration-driven data platform for reading captured source files and
mastering their evidence into governed Company, Person and relationship records.
SEC EDGAR and GLEIF are the current source-completion focus. AWS S3 and Snowflake
are the analytics deployment target.

The current executable is `edgar-warehouse`. It runs Rules, Bookkeeping, Change
Journal and Clean MDM operations, plus independent parsing and mastering workers.
The former warehouse acquisition and orchestration commands have been retired.

## Current status

Status reviewed **2026-10-04**. Implementation, local qualification and deployment
are separate milestones.

| Area | Implemented and verified | Remaining boundary |
| --- | --- | --- |
| Installable data skill | `edgartools-data` bundles the Rules creator, Rust engine, workers, Clean MDM, Bookkeeping, Change Journal and skill documents. Installed tests run without a repository checkout or `edgartools`/spaCy. | Custom parser development requires a checkout and code review. |
| Rules and control | Versioned contracts, proof/approval/activation, frozen worklists, leases, fencing, retry and independent verifier admission. | Operators approve and activate exact versions; a YAML file alone grants no execution authority. |
| Parse → master | Installed PostgreSQL 16 tests run `source.read` → `mdm.prepare` → `mdm.merge` with separate worker and verifier logins. Publication has its own worker and readback checks. | Bounded fixtures are not complete source integration or production proof. |
| Configured parsing | Rust behind Python reads XML, JSON, JSON Lines and CSV. Contracts declare paths, checks, limits, calendar dates, exact integers, booleans and parallel JSON arrays. | Source-specific semantics still need complete positive and failure equivalence. |
| SEC filing content | Merged qualification covers 14 content fields across 1,000 captured filings and 107,197 rows. | Artifact context and all 18 filing columns are locally qualified in [PR #811](https://github.com/paulananth/edgartools-platform/pull/811), pending merge. Its audit identifies six unresolved source coercion/shape differences. |
| Company / Person / GLEIF | Clean MDM and retained source readers exist; Company has a separate multisource proving run. | Complete configured read blocks, reference joins, classification, grouping and reader retirement remain unfinished. |
| AWS / Snowflake | Passive infrastructure and access roots, image publishing, native S3 pull, dbt and dashboard assets remain in the repository. | Local tests do not establish a hosted deployment, consumer cutover or production readiness. |

The full installed-bundle rerun on empty stores must reproduce **6,414 Companies,
3,052 CIK+LEI bindings and an unchanged replay**. Earlier source-reader proving
results do not satisfy that new installed-worker gate. See the
[data-skill completion ticket](.scratch/mastering-to-done/issues/21-self-sustaining-data-skill.md)
and [Company completion requirements](docs/specs/clean-mdm/company-completion.md).

## Architecture and ownership

```text
Approved Rules ──> Bookkeeping: frozen work, leases, retries, completion
                         │ task envelopes and verifier admission
Captured file receipts ──> source.read ──> mdm.prepare ──> mdm.merge
                                                               │
                                                          mdm.publish
Owners' durable delivery intent ──> Change Journal: immutable history
```

- **Rules** owns versioned source, dataset and pipeline contracts and their approval.
- **Bookkeeping** owns work and recovery. It starts without loaders, parsers or MDM;
  workers use its task protocol rather than its private database methods.
- **Workers** perform source reading and destination writes. A separate verifier
  rereads the destination and reports domain checks.
- **Clean MDM** owns governed identities, source evidence, merge decisions and
  publication intent. Commits are fenced by the worker's live lease.
- **Change Journal** records durable history. It does not own work scheduling or
  mutable master state. Delivery across stores is reconciled; it is not one
  cross-database atomic transaction.

The `source.read` profile currently accepts at most two captured artifacts and
two workers, with at most 32 MiB and 100,000 records per artifact. These are
qualification limits, not an unbounded production ingestion service.

The AWS analytics target is a separate path:

```text
Captured/warehouse objects in AWS S3
  -> Snowflake native S3 pull -> dbt gold models -> Streamlit dashboard
```

## Requirements

| Task | Requirements |
| --- | --- |
| Install and run the data bundle | `uv`, Git, Python 3.12 for the qualified runtime, and Rust `cargo` to build the native engine. Package metadata permits Python 3.12+; CI qualifies 3.12. |
| Local database qualification | PostgreSQL 16, four separate stores, migration-owner credentials, restricted worker/application roles and separate verifier roles. |
| Run the full test suite | Docker, Bash and `jq` (for infrastructure-script tests); Colima on macOS. CI explicitly pulls `postgres:16-alpine`; missing prerequisites must fail rather than skip. |
| Review and contribute | A dedicated branch/worktree, GitHub CLI `gh`, and the repository's [agent guide](AGENTS.md). |
| AWS / Snowflake operator work | AWS CLI, Terraform, Docker image tooling, Snowflake CLI, target-specific credentials and explicit rollout approval. Local mastering does not require cloud deployment. |

### Install the portable bundle

Choose a reviewed commit on `main` and set `REF` to its full SHA. This installation
uses pinned Git sources; it does not require cloning the repository.

```bash
REPO="git+https://github.com/paulananth/edgartools-platform@${REF:?Set REF to a reviewed main commit}"
uv tool install --python 3.12 "edgartools-data @ $REPO#subdirectory=packages/data-skill" \
  --with "edgartools-bookkeeping @ $REPO#subdirectory=packages/bookkeeping" \
  --with "edgartools-change-journal @ $REPO#subdirectory=packages/change-journal" \
  --with "source-contract @ $REPO#subdirectory=crates/source-contract"

edgar-warehouse --help
edgar-warehouse doctor
```

`doctor` checks the engine, skill command/flag/link references, the Rules folder
and configured stores. An unused store may be unset. A successful self-check is
not a source acceptance or deployment gate.

Use `edgar-warehouse skill install --rules <new-directory>` to install the bundled
skills and copy editable Rules. Set `EDGAR_RULES_ROOT` to that directory. Without
it, the bundle reads its packaged, read-only Rules. Follow
[Data Platform setup](skills/data-platform/SKILL.md#0-setup) for role grants,
migrations and the approval workflow. The installer preserves skills it does
not own and refuses conflicting replacements.

### Work from a checkout

```bash
git clone https://github.com/paulananth/edgartools-platform.git
cd edgartools-platform
uv sync --frozen --extra mdm --extra engine
uv run edgar-warehouse --help
```

The repository package and portable bundle have different dependency scopes.
The repository retains `edgartools` from PyPI, spaCy and warehouse/batch tooling.
The portable bundle does not depend on `edgartools` or spaCy. Rust is built only
when the engine is requested. Use `uv` for dependency management and execution.

### Stores and roles

Configure credentials outside Git and supply these environment variables:

| Store | Runtime variable | Responsibility |
| --- | --- | --- |
| Rules | `RULES_DATABASE_URL` | Versioned contracts and approval authority |
| Bookkeeping | `BOOKKEEPING_CLEAN_DATABASE_URL` | Work, leases and recovery |
| Change Journal | `CHANGE_JOURNAL_DATABASE_URL` | Durable history and receipts |
| Clean MDM | `MDM_DATABASE_URL` | Governed evidence and master state |

Migrations use owner credentials, including `RULES_MIGRATION_DATABASE_URL`,
`BOOKKEEPING_CLEAN_MIGRATION_DATABASE_URL` and
`CHANGE_JOURNAL_MIGRATION_DATABASE_URL`. Destination lease-guard installation
uses `DESTINATION_MIGRATION_DATABASE_URL`. Run MDM migrations with an owner
connection in `MDM_DATABASE_URL`; return to the application connection for runtime.
Runtime MDM uses the application role;
verification uses a separate restricted read login. See the bundled
[Bookkeeping instructions](skills/bookkeeping/SKILL.md) and
[MDM worker instructions](skills/data-platform/SKILL.md#3-master).

## Source and form scope

- **SEC Company:** `sec.submissions.company/submissions` is the sole declared
  active acquisition feed. Its declarations do not provide a live fetch worker;
  the current worker registry reads already captured files. Company integration
  also uses pinned ticker and Name Census evidence.
- **Company filing history:** `10-K`, `10-Q`, `8-K`, `20-F`, `40-F`, `6-K` and other
  forms may appear as history. They are not separate Company-mastering feeds or
  positive form-based Company rules. Person classification requires its complete
  source contract, not a guess from one form or `entityType` alone.
- **GLEIF:** captured legal-entity, relationship and reporting-exception evidence
  has its own contracts and acceptance gates. Preserve unsupported entity kinds
  as evidence instead of coercing them into Company.
- **13F:** the [information-table YAML contract](crates/source-contract/contracts/thirteenf/contract.yaml)
  reads captured XML through native Rust behind the Python worker. Parsing holdings
  does not itself create mastered Security identities or relationships.

Custom parsing is used only after a configured alternative has been tested and
shown insufficient. The skill writes a generic versioned function, tests it,
lists it in the Mapping Document, opens a PR and stops for operator code/Rules
approval. It does not activate the step itself. `rules profile`, `rules check`
and Preview against a copy of MDM remain unbuilt; use the documented manual workflow.
A general silver writer is also unbuilt: parser tables alone are not a completed
silver publication.

## Verification and completion gates

Fast checkout checks:

```bash
uv run pytest tests/unit tests/architecture
```

For full local qualification, install `jq` and keep Docker available, then sync
the CI dependencies and provision the PostgreSQL image:

```bash
uv sync --frozen --extra s3 --extra mdm-runtime --extra mdm --extra engine
docker pull postgres:16-alpine
cargo test --locked --manifest-path crates/source-contract/Cargo.toml
uv run pytest tests/unit tests/architecture tests/mdm tests/integration tests/engine
```

[CI](.github/workflows/ci.yml) keeps five jobs: Unit/Architecture, MDM, PostgreSQL
Integration, Rust/Python Engine and shell syntax checks. The aggregate CI gate
requires all five. Installed-bundle tests use isolated environments and real
PostgreSQL 16 roles; mocks or prerequisite skips do not replace that evidence.

Before declaring source completion, prove exact source outputs and failure
behavior, identity and publication invariants, outage/recovery and lease fencing,
then the full empty-store installed-worker run and unchanged replay. Retire old
readers only after those gates pass. Cloud promotion has separate infrastructure,
security, consumer readback and release requirements.

## AWS and Snowflake boundaries

Terraform separates passive infrastructure from access control. Passive roots
create infrastructure shells, not runnable ECS task definitions, Step Functions,
schedules, image rollouts or secret values. Administrators apply infrastructure
and access; deployment uses `sec_platform_deployer`; runtime uses service-assumed
roles rather than long-lived runner access keys.

Images are published with
[`infra/scripts/publish-warehouse-image.sh`](infra/scripts/publish-warehouse-image.sh).
The former AWS pipeline deploy script was retired.
[`infra/scripts/install.sh`](infra/scripts/install.sh) remains an infrastructure
setup wizard; inspect its current plan and targets before applying. The retained
Snowflake operator wrapper is
[`infra/scripts/deploy-snowflake-stack.sh`](infra/scripts/deploy-snowflake-stack.sh);
validate its target and prerequisites before applying. For dev Snowflake SQL/DDL,
use the `snowconn` connection. Credentials remain outside Terraform and Git.

The older [end-to-end runbook](docs/runbook.md),
[Company acquisition walkthrough](docs/company-only-acquisition.md) and
[Snowflake Postgres cutover runbook](docs/aws-mdm-snowflake-postgres-cutover.md)
contain historical or retired execution paths. They are not instructions for
running the current executable.

## Repository guide

| Location | Purpose |
| --- | --- |
| [skills/data-platform](skills/data-platform/SKILL.md) | Portable setup and onboard → parse → master → custom-step workflow |
| [Configured reading](skills/data-platform/READING.md) | Implemented parser grammar and qualification boundaries |
| [skills/bookkeeping](skills/bookkeeping/SKILL.md) | Loader-independent control, role grants and recovery |
| [skills/change-journal](skills/change-journal/SKILL.md) | Independent durable journal and owner-controlled recovery |
| [packages](packages) | Separately owned bundle, control and journal distributions |
| [crates/source-contract](crates/source-contract) | Native Rust engine and Python binding |
| [edgar_warehouse/workers](edgar_warehouse/workers) | External workers and destination verifiers |
| [rules](rules) | Versioned source, dataset and pipeline definitions |
| [Clean MDM specifications](docs/specs/clean-mdm/README.md) | Domain policies, evidence, Company and recovery requirements |
| [infra/terraform](infra/terraform) | AWS/Snowflake passive and access roots |
| [infra/snowflake](infra/snowflake) | Native pull, dbt gold and dashboard assets |
| [tests](tests) | Unit, architecture, MDM, PostgreSQL and engine acceptance |

Follow [AGENTS.md](AGENTS.md) before changing the repository. Use a dedicated
runtime branch and worktree, preserve unrelated changes and open a PR; do not
commit directly to `main`.
