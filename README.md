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

## Architecture

Captured files are evidence. An approved Rules version says how to read them.
Bookkeeping freezes the work, hands each unit to a worker, and admits a
verifier's read-back before the unit is complete. Clean MDM masters identities.
Reference data and silver are separate landings. The analytics path reads
warehouse objects; it does not decide an identity.

```text
Captured files
      |
      v
Approved Rules ---------------- Bookkeeping
      |                         frozen work, lease, retry
      v                              |
source.read                          v
Rust, called from Python             verifier read-back
      |
      +---- source.combine          when one feed joins several readings
      |
      +---- reference data          pinned codes and hierarchies
      |
      +---- silver land             flat rows on local PostgreSQL
      |
      v
mdm.prepare ---- mdm.merge ---- mdm.publish
                                      |
                                      v
                               Change Journal
                               durable history of delivery intent

Analytics, separate from mastering:

S3 warehouse objects --> Snowflake native pull --> dbt gold --> Streamlit
```

Rules own the versioned contracts. Bookkeeping owns work and recovery, and
starts without a parser or a master record. Workers read and write. A separate
verifier rereads the destination. Clean MDM owns identities, evidence, merge
decisions and publication intent, and each commit checks the worker's live
lease. The Change Journal records history. Silver lands an approved spec on
local PostgreSQL and does not commit a master.

## Parsing

Configured reading runs in Rust (`crates/source-contract`). On 2026-10-02
the platform chose one engine, built before the next per-source parser, with
Rust under the cover and Python as the only caller. An approved rules file
states the format, the container, the document checks, the tables, the
columns, and the record checks. `edgar_warehouse/rules/source_engine.py` is
the facade. Bookkeeping, the rules commands, and Clean MDM reach a reading
through that facade. Calls into the edgartools package stay in Python. A
custom step is a named Python function, used when the rules file cannot state
the field.

The engine reads XML, JSON, JSON Lines, CSV, and one zip member. An ordinary
read holds the artifact in memory up to the contract's byte and record limits
and fails closed past those limits. A large captured JSON array or XML
envelope can declare streamed framing: Rust frames each record inside the
limits that framing declares, and Python receives the projected reading. Publication
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

Each source record waits in the Source Stage as its newest reading, unbound,
until a rule links it to an identity. Bronze keeps what that source said
before. The Merge Stage is the only writer of master state. One fenced
transaction resolves the identity, selects fields, writes relationships whose
endpoints are already accepted, records the decision, and enqueues publication.

```text
Captured record
      |
      v
Source Stage
newest reading of that source record
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
Publication intent ----> Change Journal
```

A proved name rule may bind when the operator has approved that exact version.
Anything less stays with a steward. Old readers stay until an installed
empty-store replay matches the mastered result.

## Install

Install is not final. The bundle, a checkout, the stores, and the local
qualification commands will be written here once install is completed.

## Evidence and custom steps

Workers read files that are already captured. Filing history is evidence for a
Company or a Person. A form name does not classify a Person. GLEIF evidence
that is not a Company stays evidence.

A custom parsing step is written only after configured reading cannot state
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
| [Configured reading](skills/data-platform/READING.md) | Implemented parser grammar and qualification boundaries |
| [Combining readings](skills/data-platform/COMBINING.md) | Keyed collections and joins across readings |
| [skills/data-profiling](skills/data-profiling/SKILL.md) | Classify a captured data set before onboarding |
| [edgar_warehouse/silver_writer](edgar_warehouse/silver_writer) | Local PostgreSQL 16 landing from an approved silver spec |
| [skills/bookkeeping](skills/bookkeeping/SKILL.md) | Loader-independent control, role grants and recovery |
| [skills/change-journal](skills/change-journal/SKILL.md) | Independent durable journal and owner-controlled recovery |
| [packages](packages) | Separately owned bundle, control and journal distributions |
| [crates/source-contract](crates/source-contract) | Rust source engine; Python is the only caller |
| [edgar_warehouse/workers](edgar_warehouse/workers) | External workers and destination verifiers |
| [rules](rules) | Versioned source, dataset and pipeline definitions |
| [Clean MDM specifications](docs/specs/clean-mdm/README.md) | Domain policies, evidence, Company and recovery requirements |
| [infra/terraform](infra/terraform) | AWS/Snowflake passive and access roots |
| [infra/snowflake](infra/snowflake) | Native pull, dbt gold and dashboard assets |
| [tests](tests) | Unit, architecture, MDM, PostgreSQL and engine acceptance |

Follow [AGENTS.md](AGENTS.md) before changing the repository. Use a dedicated
runtime branch and worktree, preserve unrelated changes and open a PR; do not
commit directly to `main`.
