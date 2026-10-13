# EdgarTools Platform

A configuration-driven platform for decision-support facts used by trading
agents and by people auditing those facts. Agents profile a captured data set
and onboard it, generically, into Clean MDM (identities and relationships),
reference data, or silver. SEC EDGAR and GLEIF are the current
source-completion focus. AWS S3 and Snowflake are the analytics deployment
target. A local mastering proof does not authorize that deployment.

Operators approve and activate exact Rules versions. A YAML file alone grants
no execution authority. The skills state each step generically; today's sources
are examples, not hardcoded steps. A proven name rule may bind only with
measured proof and operator approval. A name lookup id never binds.

The current executable is `edgar-warehouse`. It runs Rules, Bookkeeping, Change
Journal, Clean MDM and local silver operations, plus independent parsing and
mastering workers.

The [configured capture guide](docs/configured-capture.md) documents the
registered HTTPS JSON worker, offline qualification and pending Company
acquisition integration.

## Architecture

Ingest acquires one source file and keeps the verified bytes as bronze.
An approved Rules version says how to read that file. Bookkeeping freezes
the work, hands each unit to a worker, and admits a verifier's read-back
before the unit is complete. Silver is the flat landing of those rows.
Clean MDM masters identities from the source extract. Reference data is
its own landing. The analytics path reads warehouse objects and does not
decide an identity.

```text
Ingest
one source file, hash verified
      |
      v
Bronze
one immutable captured file
      |
      v
Approved Rules            Bookkeeping                 Change Journal
how that file is read     restart: frozen work,       what changed: a file
      |                   lease, retry, verifier      already processed under
      |                   read-back                   the same rules and shared
      |                                               inputs is skipped
      |                   (both stand beside every step below)
      v
source.read
source extract, Rust, called from Python
      |
      +---- source.combine           when one feed joins several source extracts
      |
      +---- Silver                   flat rows on local PostgreSQL
      |                              landed by hand from an approved spec
      |
      +---- reference data           pinned codes and hierarchies

Mastering, from the source extract:

mdm.prepare ---- mdm.merge ---- journal.record ----> Change Journal
                     |                               each file processed
                     v
                mdm.publish ----> consumers: only the records that changed
                     |            (or every record, on a forced publish)
                     +----------> the MDM Change Journal: the whole batch

Analytics, separate from mastering:

S3 warehouse objects --> Snowflake native pull --> dbt gold --> Streamlit
```

Rules own the versioned contracts. Bookkeeping owns work and recovery, and
starts without a parser or a master record. Workers read and write. A separate
verifier rereads the destination. Clean MDM owns identities, evidence, merge
decisions and publication intent, and each commit checks the worker's live
lease. Bookkeeping and the Change Journal are peers over every step:
Bookkeeping restarts a load where it stopped, and the Change Journal decides,
for a whole file or source, whether it is identical (skip it) or must be
processed. A change in how a source is read, or in a shared input, processes
every file again; `--all` forces every file, and the journal records the force.
It never decides at field level. Silver lands an approved spec by hand on
local PostgreSQL and does not commit a master. The pipeline worker for that
landing is not built.

## Parsing

Configured source extract runs in Rust (`crates/source-contract`). On 2026-10-02
the platform chose one engine, built before the next per-source parser, with
Rust under the cover and Python as the only caller. An approved rules file
states the format, the container, the document checks, the tables, the
columns, and the record checks. `edgar_warehouse/rules/source_engine.py` is
the facade. Bookkeeping, the rules commands, and Clean MDM reach a source extract
through that facade. Calls into the edgartools package stay in Python. A
custom step is a named Python function, used when the rules file cannot state
the field.

The engine reads XML, JSON, JSON Lines, CSV and Parquet, one member of a zip
archive, and the XML document inside an SEC SGML submission file. An ordinary
read holds the artifact in memory up to the contract's byte and record limits
and fails closed past those limits. A large captured JSON array or XML
envelope can declare streamed framing: Rust frames each record inside the
limits that framing declares, and Python receives the projected source extract. Publication
waits for a valid end of file. Streamed framing does not activate a source.

HTML filings, layout-heavy extracts, and prose stay on their Python parsers.
The Rust engine performs the mechanical read the rules file describes.

## Data model

Company and Person are the identities this platform masters. A profile hangs
on one of those identities and is the same identity, not a second one. A
filing or a GLEIF file is evidence for that mastering.

```text
Company -------------------------------- Person
  |                                        |
  | Adviser profile                        | Adviser profile
  | Audit Firm profile                     |   when the adviser is a natural person
  | Fund profile                           |
  |   when the fund is itself a company    | EMPLOYED_BY
  |                                        | BENEFICIAL_OWNER_OF
  | AUDITED_BY                             |
  | IS_SUBSIDIARY_OF                       |
  | IS_DIRECTLY_CONSOLIDATED_BY            |
  |                                        |
  +---------------- HOLDS -----------------+
                    one reported period

A subsidiary, a filing trust, and its adviser are separate Companies
when they have separate identifiers.
A rename of one identifier stays one Company. The old name is an alias.
```

Security, Fund Structure, Branch, Government Entity, International
Organization, and Market/Venue are accepted domains for later. They are not
running masters. A share class is not a field of its Company. Ownership, the
accounting parent, and a GLEIF fund link are different relationships.

## Mastering and merging

Each source record waits in the Source Stage as its newest source extract, unbound,
until a rule links it to an identity. Bronze keeps what that source said
before. The Merge Stage is the only writer of master state. One fenced
transaction resolves the identity, selects fields, writes relationships whose
endpoints are already accepted, records the decision, and enqueues publication.

```text
Captured record
      |
      v
Source Stage
newest source extract of that source record
unbound until a matching rule links it
      |
      v
Merge Stage
one transaction, under the worker's live lease
  resolve the identity
  select fields and keep the disagreement
  write relationships with accepted endpoints
  record why this master is the result
      |
      +---- linked ----> Company or Person
      |                    plus aliases
      |
      +---- short of proof --> stays unbound, or goes to a steward
      |                        a name lookup id never creates an identity
      |
      v
Publication intent
  each consumer gets only the records the batch inserted or changed
  the MDM Change Journal gets the whole batch, as history
  `mdm force-publish` sends every current record to one consumer
```

A proved name rule may bind when the operator has approved that exact version.
Anything less stays with a steward. Old readers stay until an installed
empty-store replay matches the mastered result.

## Sources

| Source | Read by | Mastered |
| --- | --- | --- |
| SEC submissions, Company | `rules/sources/sec.submissions.company` | Company (by CIK), on the `mastering` target (also `capture`, `mdm`) |
| SEC submissions, Person | `rules/sources/sec.submissions.person` | Person (by CIK), on the `mastering` target |
| GLEIF Golden Copy (Level 1, relationships, reporting exceptions) | `rules/sources/gleif` | Company (by LEI) and its parents |
| IAPD Form ADV (filings, custodians) | `rules/sources/iapd.adv` | drafted, not switched on |
| SEC Forms 3, 4 and 5 | `rules/sources/sec.ownership` | read only; its Dataset Contracts are next |

Reference data the readings pin lives in `rules/reference/published/` (RDM
code sets, each pinned by sha256).

## Install

[`infra/scripts/install.sh`](infra/scripts/install.sh) prints the ordered
install plan (`plan`), checks the workstation (`doctor`) and, with `deploy
--apply`, runs each stage after a yes. Its stages provision AWS and Snowflake,
publish the images, build dbt gold and the dashboard, then create and upgrade
the six PostgreSQL 16 stores the configured platform runs on: Rules,
Bookkeeping, Change Journal, RDM, silver, and Clean MDM with Bookkeeping's
lease guard. Each schema is created and upgraded as its owner, through the
store's own migration variable (`RULES_MIGRATION_DATABASE_URL`,
`BOOKKEEPING_CLEAN_MIGRATION_DATABASE_URL`,
`CHANGE_JOURNAL_MIGRATION_DATABASE_URL`, `RDM_MIGRATION_DATABASE_URL`,
`SILVER_MIGRATION_DATABASE_URL`; for MDM, `MDM_DATABASE_URL` set to its owner,
and `DESTINATION_MIGRATION_DATABASE_URL` for the guard). The runtime logins use
the plain variables (`RULES_DATABASE_URL`, `BOOKKEEPING_CLEAN_DATABASE_URL`,
`CHANGE_JOURNAL_DATABASE_URL`, `RDM_DATABASE_URL`, `SILVER_DATABASE_URL`,
`MDM_DATABASE_URL`). All are set outside the script; `edgar-warehouse doctor`
must then print `"ok": true`. The four stores every feed needs are Rules,
Bookkeeping, Change Journal and MDM; RDM and silver are needed by the readings
that pin code sets and by silver landing.

Not yet in the plan: the worker runtime on AWS. The old pipeline's ECS task
definitions and Step Functions were retired with its commands (platform
validation 2b); the configured workers' launch configuration waits for the
operator's AWS destinations. Today a feed runs with the Bookkeeping skill's
**run** mode ([skills/bookkeeping/RUN.md](skills/bookkeeping/RUN.md)).

## Evidence and custom steps

Workers read files that are already captured. Filing history is evidence for a
Company or a Person. A form name does not classify a Person. GLEIF evidence
that is not a Company stays evidence.

A custom parsing step is written only after configured source extract cannot state
the field. The skill adds one generic versioned function, tests it, lists it
in the Mapping Document, opens a pull request, and stops. The operator approves
the code and the Rules version.

## AWS and Snowflake boundaries

Terraform separates passive infrastructure from access control. Passive roots
create infrastructure shells, not runnable ECS task definitions, Step Functions,
schedules, image rollouts or secret values. Administrators apply infrastructure
and access; deployment uses `sec_platform_deployer`; runtime uses service-assumed
roles rather than long-lived runner access keys.

Publish images with
[`infra/scripts/publish-warehouse-image.sh`](infra/scripts/publish-warehouse-image.sh).
The Snowflake operator wrapper is
[`infra/scripts/deploy-snowflake-stack.sh`](infra/scripts/deploy-snowflake-stack.sh).
Credentials stay outside Terraform and Git. Older runbooks in `docs/` describe
retired execution paths.

## Repository guide

| Location | Purpose |
| --- | --- |
| [skills/data-platform](skills/data-platform/SKILL.md) | Portable setup and onboard → parse → master → custom-step workflow |
| [Configured source extract](skills/data-platform/READING.md) | Implemented parser grammar and qualification boundaries |
| [Runtime responsibilities](docs/architecture/runtime-responsibilities.md) | Current Rust, Python and database owners, evidence and migration prerequisites |
| [Combining source extracts](skills/data-platform/COMBINING.md) | Keyed collections and joins across source extracts |
| [skills/data-profiling](skills/data-profiling/SKILL.md) | Classify a captured data set before onboarding |
| [edgar_warehouse/silver_writer](edgar_warehouse/silver_writer) | Local PostgreSQL 16 landing from an approved silver spec |
| [skills/bookkeeping](skills/bookkeeping/SKILL.md) | Loader-independent control, role grants and recovery |
| [skills/change-journal](skills/change-journal/SKILL.md) | Independent durable journal and owner-controlled recovery |
| [packages](packages) | Separately owned bundle, control and journal distributions |
| [crates/source-contract](crates/source-contract) | Rust source engine; Python is the only caller |
| [edgar_warehouse/workers](edgar_warehouse/workers) | External workers and destination verifiers |
| [rules](rules) | Versioned source, dataset and pipeline definitions |
| [Clean MDM specifications](docs/specs/clean-mdm/README.md) | Domain policies, evidence, Company and recovery requirements |
| [Reference data (RDM)](docs/specs/rdm/spec.md) | Code sets, approved versions, hierarchies and crosswalks |
| [infra/terraform](infra/terraform) | AWS/Snowflake passive and access roots |
| [infra/snowflake](infra/snowflake) | Native pull, dbt gold and dashboard assets |
| [tests](tests) | Unit, architecture, MDM, PostgreSQL and engine acceptance |

Follow [AGENTS.md](AGENTS.md) before changing the repository. Use a dedicated
runtime branch and worktree, preserve unrelated changes and open a PR; do not
commit directly to `main`.
