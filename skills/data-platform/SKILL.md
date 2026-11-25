---
name: data-platform
description: Guide data work from current readiness to verified operation. Use for service URLs, .env discovery, connection setup, onboarding, custom parsing, cross-reference readiness, processing captured files, turning drafts into tested and approved releases, activation, deployment or recovery. Coordinates data-onboarding, refining-rules, data-operations, MDM engineering, Bookkeeping and Change Journal.
---

# Data Platform

One installed package, `edgartools-data`, holds everything this skill runs:
the rules creator, the configured engine, the workers, Bookkeeping, the
Change Journal, MDM, and these skills. Feed work uses the installed package.
Persistent local testing and custom parsing steps (Mode 6) use a repository
checkout.

## Hard stops

Each rule below has one home, named beside it; this list grants no permission.

- **Approval and activation:** Data Platform approves nothing; each approval belongs to the phase that asks for it.
  Never activate or switch on a rules version for the operator: that consent is theirs, given only when asked
  (`CONTEXT.md`, "Rule Activation Approval"), on a passing test run ("Proving Run"), with a digest shown beside its
  plain-words explanation (`CLAUDE.md`, "Talking with the operator").
- **Provider access:** no request to a provider (its site, API or documentation) without the operator's permission
  for that request (`CLAUDE.md`, "Commits, PRs and secrets").
- **Secrets:** read a credential from configuration, never print it; the operator sets a missing one in their own
  terminal ([Connection URLs and environment](#connection-urls-and-environment)).
- **Configuration only, no data value in public, no guessed identifier, no invented command, one question at a
  time:** the [data-onboarding hard stops](../data-onboarding/SKILL.md#hard-stops).

## Start here: route the work

Inputs: the requested source and work, its configuration and retained run evidence, [Source readiness](#source-readiness), the
skills index (`skills/README.md` in a checkout; an installed copy is already the chosen skill) and the variable names in [Connection setup](CONNECTIONS.md). Output: one next action, its owner
and the environment checks it needs. A route grants no approval, provider request or switch-on.

1. **Find the state.** With no `edgar-warehouse` on the path, the next action is [Setup](#0-setup), step 1. A source is
   configured when the rules folder (`EDGAR_RULES_ROOT`, else the bundle's read-only copy) holds `sources/<source>/source.yaml`;
   a run id with Bookkeeping status is retained run evidence; a log's `## Resume` record is checked by [Resume](RESUME.md).
2. **Route** with `edgar-warehouse plan route --request <file>` (or `--request -`). Supply booleans for source configuration, delivery change and live-rule change, derived from retained evidence. No config routes to Data Onboarding; for configured sources, a live-rule change routes to Refining Rules, a changed delivery or repeat run to Data Operations, and both change flags to operator clarification.
   For `resume`, supply ordered phases (`owner`, `action`, `complete`, `hashes_match`); skip matching completed phases and choose the first unfinished/invalidated. The command only selects a route; it performs no load, provider request, approval or switch-on. Hand off to its owner/action; include no identifiers, data values or secrets.
3. **Name the duty** in the [duty table](CONNECTIONS.md#database-connections-and-duties) (none to read captured files; a load
   or a worker: Loader, `worker.env`). Check, without printing a value, that its file exists and sets `DATA_URL`, `CONTROL_URL` and `CONFIG_URL`.
4. **Run `edgar-warehouse doctor`**, with that file, if any, sourced in a command-scoped subshell. Expected: exit 0 with `"ok": true`,
   `unresolved` empty, `engine` `loads`, `rules_root.exists` true, and `answers` for each of `rules`, `bookkeeping`,
   `change_journal` and `mdm` under `stores` (`not set` passes for a store the action does not use; RDM and silver are not probed).
5. **Hand off** the existing artifact and its location to the owner; never recreate it to cross a skill boundary.

**Stop** and name the blocker to its owner when the state fits no owner or two (one question to the operator); the duty file or a
variable is missing (the operator sets it in their own terminal); doctor prints `"ok": false` (an `unresolved` line is the
[Self-check](#7-self-check)'s fix; a store that `does not answer` is reported by name and error kind); a rules change finds
`rules_root.bundled_read_only` true ([Setup](#0-setup), step 2); the action needs a provider request, approval or switch-on not
given ([Hard stops](#hard-stops)); or the processing asked lacks the evidence [Source readiness](#source-readiness) requires.

## The seven wastes

Every skill works lean (operator: "make all skills understand 7
wastes and eliminate any of the waste from each skill"). Before a step, check
it against the seven, and drop what adds no value:

| Waste | Here | Instead |
|---|---|---|
| Transport | Copying captures, stores or files to new places for each check | Read the capture where it is; reuse a store |
| Inventory | Branches, worktrees, stores, drafts and tickets left open | Finish or close each; stop and remove what a run left |
| Motion | Searching code for what a skill should say; rebuilding inputs a run already made | Write the answer into the skill once; keep a run's inputs with its report |
| Waiting | Runs that stop on a deadline too short; questions a ruling already answers | Size the deadline from the measured time; decide what follows from a ruling |
| Over-processing | The rest of a delivery after its tests, a slice, and each new case are already proved | The cheapest proof (`mdm-engineering`); [a sample chosen by kind](../data-profiling/SKILL.md#choose-a-proof-sample-by-kind); carry a proof forward |
| Over-production | Building a feature, a target, a check or a Gold table before a source or question needs it | Build only what the step in hand needs |
| Defects | Guessed times, unchecked limits, a skill word CI refuses: rework | Read the clock; check bounds first; run the checks the change can affect |

**Find the root cause** of every surprise, failure and disagreement of two readings by the [five whys](ROOT-CAUSE.md), silently.

**Carry a proof forward** instead of running it again: when and how is in
[mdm-engineering](../mdm-engineering/SKILL.md#choose-the-cheapest-proof),
"Choose the cheapest proof", its last row.

For catalog restoration, Mapping Documents, entity domains, glossaries, quality
publication, unclear asset names or coverage of all entities and pipelines, use
[Business catalog](../data-onboarding/CATALOG.md).

## Source readiness

When running, recovering or qualifying a source, apply these operator requirements. They are acceptance rules; identify missing runtime enforcement as
an implementation gap before calling a source ready.

- Qualify retained local captures through genuine provenance, completeness
  evidence. Local processing qualification can
  precede AWS capture qualification. A provider request needs its own
  permission ([Hard stops](#hard-stops)); missing evidence blocks affected processing.
- Require the common configuration-driven path through dependencies, reading,
  mastering, merge, independent verification and Journal recording. Run declared
  approved dependencies from available local captures before freezing consumer
  inputs. Report any separate preparation command still required as a gap.
- Call a source locally ready only after its entire declared retained delivery
  is processed and verified, with accepted/waiting/rejected records accounted
  for, and an unchanged repeat selects zero files and starts no mastering work.
  Passing code/fixture tests is implementation evidence. Full retained delivery
  and full provider history are separate claims. Keep qualification artifacts
  private and report counts publicly.
- Preserve original required versions throughout completion and resume.
  Ordinary supersession leaves those pins intact. Explicit invalidation stops
  affected work and makes affected outputs unavailable as dependencies until
  repaired. Preserve history and verified progress, correct through the normal
  processing path with valid approved inputs, and let unrelated work continue.
  Never silently repin or clear shared data to repair affected work.

## Decisions, artifacts and handoffs

Data Platform owns the route and its entry checks ([Start here](#start-here-route-the-work)), not the next skill's procedure.

| Decision or artifact | Authoritative owner | Handoff |
|---|---|---|
| Is this setup/connection discovery, new-source onboarding, a live-rule change, recurring operation, or recovery? | Data Platform routes from current source configuration and retained run evidence. | Follow the matching row below; use [Connection setup](CONNECTIONS.md) for connection discovery. |
| Private service addresses, environment files and database duty | Data Platform, [Connection setup](CONNECTIONS.md). | The owning procedure receives only the selected duty and connection variable names; credentials stay in private configuration. |
| Capture inventory, profile findings, field evidence and the profile report | [Data Profiling](../data-profiling/SKILL.md), which reads data and writes findings. | New data set: pass the captured inputs to [Data Onboarding](../data-onboarding/SKILL.md), which consumes the retained `REPORT.md` and `findings.yaml`. A changed delivery to a live feed goes to [Refining Rules](../refining-rules/SKILL.md)'s compare path. |
| New feed/domain decisions, source/merge/pipeline rules, mappings, checks, metadata and target registration | [Data Onboarding](../data-onboarding/SKILL.md). | Start from its retained discovery and profile artifacts; it owns the new configuration and the scoped checks/load handoff. |
| Changes to a live feed's mapping, quality or matching rules; comparison against approved findings | [Refining Rules](../refining-rules/SKILL.md). | Keep the approved configuration and compare report with the rule change; return to its check-and-load path when ready. |
| Repeated loads, operational readiness, run status, recovery and operational handoff | [Data Operations](../data-operations/SKILL.md). | Use the existing source runbook, Bookkeeping/Journal evidence and retained delivery; do not restart completed work just to recreate its evidence. |
| Execution contract and run-control semantics, including unit state, completion and recovery | [Bookkeeping](../bookkeeping/SKILL.md) and [Change Journal](../change-journal/SKILL.md) define those contracts; Data Operations owns their operational use. | Carry the run identifier, completed-unit evidence and Journal receipt to Data Operations; use the owning contract skill to interpret or change semantics. |
| Changes to MDM engine behavior, persistence or merge implementation | [MDM Engineering](../mdm-engineering/SKILL.md). | Carry the demonstrated behavior gap and qualification evidence; source onboarding and run execution do not own engine changes. |
| Shared source readiness requirements and the route to the owning phase | Data Platform, [Source readiness](#source-readiness). | The phase owner records its own evidence; Data Platform does not certify operational readiness from instructions or fixture tests. |

Route by the current state, not only the source's age:

- **New captured source:** the retained capture location and provenance receipt go to
  [Data Onboarding](../data-onboarding/SKILL.md#the-files-are-the-rules), which invokes
  [Data Profiling](../data-profiling/SKILL.md#modes) and keeps its `REPORT.md` and `findings.yaml`.
- **Configured source:** a repeat delivery or run goes to Data Operations with the source runbook, delivery location and
  latest Bookkeeping/Journal status ([live state](../data-operations/SKILL.md#start-with-live-state)); a live-rule change
  goes to [Refining Rules](../refining-rules/SKILL.md#modes) with the approved configuration, changed delivery and compare report.
- **Restart after a stop:** the source log's `## Resume` record names the first unfinished action and its owner;
  [Resume](RESUME.md) says when each recorded result is reused, reopened or blocked. A completed phase is not repeated.

These are routing examples, not qualifications or evidence: a phase is complete only under its owning skill's rules.

## The flow

For recurring loads, backlog/resource sizing, renamed files, run monitoring and
operational handoff, use [data-operations](../data-operations/SKILL.md). It
coordinates this flow and the existing Bookkeeping/Change Journal skills;
AWS acquisition supplies completed deliveries separately. To install, enable
and run one source, then clear a finished test, follow
[Install and enable one source](../data-operations/SKILL.md#install-and-enable-one-source).

For an incident diagnosis or a gap in operational telemetry, use
[production-support](../production-support/SKILL.md). It diagnoses from
Bookkeeping, Change Journal and destination evidence; it does not add an
alerting integration or replace the normal run verifier.

| Step | Mode | Detail in |
|---|---|---|
| 0 | Setup, once per machine | this file |
| 1 | Onboard a new feed or kind | [data-onboarding](../data-onboarding/SKILL.md) |
| 1b | Change a live feed's rules | [refining-rules](../refining-rules/SKILL.md) |
| 2 | Parse: read captured files with the configured engine | [data-operations](../data-operations/SKILL.md) owns the run procedure; [bookkeeping RUN](../bookkeeping/RUN.md) owns execution contract semantics. The Parse section below is reference only. |
| 2b | Combine keyed collections and join configured source extracts | [COMBINING.md](COMBINING.md) |
| 3 | Master: the parsed records into MDM | [data-operations](../data-operations/SKILL.md) owns the run procedure; [MDM Engineering](../mdm-engineering/SKILL.md) owns engine behavior and persistence. The Master section below is reference only. |
| 4 | Check the rules files and load | [data-onboarding](../data-onboarding/LOAD.md) owns onboarding checks; [data-operations](../data-operations/SKILL.md) owns recurring loads. |
| 5 | Recover a run | [data-operations](../data-operations/SKILL.md) owns operational recovery, using [Bookkeeping recovery](../bookkeeping/RECOVERY.md) and [Change Journal](../change-journal/SKILL.md) contracts. |
| 6 | Custom parsing, only when the engine cannot state a field | [data-onboarding](../data-onboarding/SKILL.md) owns the source-specific change workflow; [MDM Engineering](../mdm-engineering/SKILL.md) owns reusable engine primitives. |
| 7 | Self-check | this file |

## Connection URLs and environment

Before discovering or configuring any service URL, `.env`, connection profile
or database duty, read [Connection setup](CONNECTIONS.md). Data Platform is
the sole owner of these instructions, including the one loader login and who may open the stores folder; other
skills link here.

## 0. Setup

Before selecting tables for managed mirroring or AutoOntology, apply
[Final exposable tables](FINAL-TABLES.md): one configuration-owned table list
for both consumers, projected into OpenMetadata.

Reusable workflow helpers live in the owning skill's `scripts/` directory or
the application package, not `infra/`. Keep only deployment wiring under
`infra/`; pass deployment configuration explicitly to generic helpers.
A skill's script is generic and decoupled: it takes every input (a configuration file, a name, an instance) as an
argument, holds no name, path or constant of one deployment, and does one thing. Nothing in a skill is hardcoded: a
database, role, instance, mirror, schema or account name is read from configuration (for Snowflake, `rules/snowflake.yaml`) and the skill
says where to read it. The skill's procedure comes first, in
words; a script exists only to run a step of that procedure the same way every time, never to do work the procedure
does not describe. A step with no script yet is written into the skill before it is done by hand or by one-off code.
Before shipping a skill, verify its links in an isolated installed skill tree:
a checkout can hide a missing helper by resolving a link back into `infra/`.

For Snowflake-hosted PostgreSQL, direct managed Iceberg mirror consumption and
required dbt Gold transformations,
read [Hosted PostgreSQL mirroring](HOSTED-MIRRORING.md). It routes to the
installed `snowflake-postgres` skill; source hosting, resizing, mirror creation
and Gold qualification have separate readiness and approval gates.

For persistent local agent environments, baseline promotion or recovery, read
[Local testing](LOCAL-TESTING.md). It defines automatic promotion after verified
checks and points to the repository lifecycle script.

1. **Install.** The engine is Rust: `cargo` must be on the path (install it
   from rustup.rs if `cargo --version` fails). Pick the git ref to install
   (a commit on `main`), then:

   ```bash
   REF=<commit>
   REPO=git+https://github.com/paulananth/edgartools-platform@$REF
   uv tool install --python 3.12 "edgartools-data @ $REPO#subdirectory=packages/data-skill" \
     --with "edgartools-bookkeeping @ $REPO#subdirectory=packages/bookkeeping" \
     --with "edgartools-change-journal @ $REPO#subdirectory=packages/change-journal" \
     --with "edgartools-control-core @ $REPO#subdirectory=crates/control-contract" \
     --with "source-contract @ $REPO#subdirectory=crates/source-contract"
   ```

   Building the engine takes about two minutes. It worked when
   `edgar-warehouse --help` lists `rules`, `load`, `bookkeeping`, `mdm`,
   `workers`, `plan` and `doctor`.

   Each wheel ships a list of files, not a folder:
   `packages/<wheel>/pyproject.toml`'s `force-include`. When you add a
   module that the command line imports, add it to its wheel's list too.
   Otherwise the installed `edgar-warehouse` fails on import, though every
   test run from a checkout passes. The bundle tests
   (`tests/engine/test_data_skill_bundle_postgres.py`) install from the
   committed head and catch it.

2. **Skills and rules folder.** `edgar-warehouse skill install --rules <new folder>`
   copies these skills into `~/.agents/skills` and `~/.claude/skills`, and the
   rules the bundle was built with into the new folder. It refuses to replace
   a skill it did not install (an older `link.sh` link): remove that link
   first, or keep using the linked copy. Then
   `export EDGAR_RULES_ROOT=<that folder>`. Without it, the bundle reads its
   own read-only copy of the rules.

3. **Engine and container.** Use the operator's selected database:
   PostgreSQL, MySQL or SQL Server Express. Select **test** or **production**
   separately. A request for all three means three independent targets. Keep
   that selection through database creation, schema initialization and domain
   operation; a PostgreSQL-only command is a runtime gap to repair, not a
   reason to substitute PostgreSQL. Check the selected engine's actual store
   capabilities with [STORES.md](STORES.md).

   This skill starts the selected container. Use the Docker context already
   configured. Leave `DOCKER_HOST` unset. Do not pass a worktree path, an
   agent name, or an owner label. If that container already exists, start it.
   Do not create a second container with the same name.

   | Instance | PostgreSQL | MySQL | SQL Server Express |
   |---|---|---|---|
   | test | `edgartools-test-postgres` | `edgartools-test-mysql` | `edgartools-test-sqlserver` |
   | production | `edgartools-prod-postgres` | `edgartools-prod-mysql` | `edgartools-prod-sqlserver` |

   The volume name is the container name plus `-data`. A password lives in a
   private mode `0600` file and is never printed or committed.

   ```bash
   docker pull postgres:16-alpine
   docker volume create <container>-data
   docker run -d --name <container> --restart unless-stopped \
     -p 127.0.0.1::5432 \
     --env-file <private-postgres-env> \
     -v <container>-data:/var/lib/postgresql/data \
     postgres:16-alpine
   ```

   The private file sets `POSTGRES_PASSWORD`. For a PostgreSQL selection,
   MDM, RDM, Rules, Bookkeeping, the Change Journal and silver use this
   container. A MySQL or SQL Server selection uses its own container for
   those stores, subject to the runtime capability check above.

   Start MySQL only when the task names MySQL. Start SQL Server Express only
   when the task names SQL Server. They are separate containers. Express is
   limited to 10 GB per database.

   ```bash
   docker pull mysql:8
   docker volume create <container>-data
   docker run -d --name <container> --restart unless-stopped \
     -p 127.0.0.1::3306 \
     --env-file <private-mysql-env> \
     -v <container>-data:/var/lib/mysql \
     mysql:8
   ```

   ```bash
   docker pull mcr.microsoft.com/mssql/server:2022-latest
   docker volume create <container>-data
   docker run -d --name <container> --platform linux/amd64 --restart unless-stopped \
     -p 127.0.0.1::1433 \
     --env-file <private-sqlserver-env> \
     -v <container>-data:/var/opt/mssql \
     mcr.microsoft.com/mssql/server:2022-latest
   ```

   The MySQL file sets `MYSQL_ROOT_PASSWORD`. The SQL Server file sets
   `ACCEPT_EULA=Y`, `MSSQL_PID=Express`, and `MSSQL_SA_PASSWORD`. On Apple
   Silicon, SQL Server runs as `linux/amd64`.

   You may remove a **test** container and its volume when the test is
   finished. You do not remove a **production** container. You do not remove
   its volume. You do not stop it to clear a worktree.

4. **Databases.** On each selected engine's container, create these databases
   when they are missing: `rules`, `bookkeeping`, `change_journal`, `mdm`, `rdm`,
   and `silver`. Do not paste the statement or an address into the chat. Then
   apply the store schemas and create every committed silver table by
   [STORES.md](STORES.md): only this skill and data-onboarding create tables,
   and a load creates none. Use [Connection URLs and environment](#connection-urls-and-environment)
   for addresses, credentials and role selection. Database creation requires
   an authorized owner with `CREATEDB`; create only missing databases and
   preserve existing data.

5. **Check.** `edgar-warehouse doctor` must print `"ok": true`. It lists any
   command a skill names that does not exist, whether the engine loads, the
   rules folder in use, and which stores answer (`not set` is fine for a store
   the task does not use).

6. **Local test server.** For loads on a machine, initialize the one local store
   all sources load into: the `local-test-server`. Its name is configuration
   (`EDGARTOOLS_LOCAL_TEST_SERVER`, default `local-test-server`), never typed into
   a command or a rules file:

   ```bash
   uv run --extra mdm python infra/scripts/local-test-stores.py up
   ```

   It prints the store's state and the env file's path, never a login. The folder
   beside that file is what `load --stores` takes ([Local testing](LOCAL-TESTING.md#the-local-test-server)).

## 2. Parse

A feed is parsed by the `source.read` worker: the configured engine reads
each captured file by the feed's contract (its `read:` block) and writes the
tables and the records set aside. Nothing feed-specific runs. Read
[Configured source extract](READING.md) before writing the contract: it covers
complete JSON records, column arrays, exact source text and frozen references.

1. The changed pipeline document passes the local changed-document guard; CI checks the full Rules tree.
2. Submit: `edgar-warehouse rules run --pipeline <name> --target <target> --input-manifest <uri> --input-sha256 <sha256>`.
   Keep the `run_id` it prints.
3. Work, as the worker login:
   `edgar-warehouse workers work source.read <run_id> --reports <uri> --limit 100`.
   The worker checks each unit it wrote and completes it.
4. Repeat until every read unit is verified; the limit bounds
   one invocation. For a read-only target, finish with
   `edgar-warehouse bookkeeping finalize <run_id>` and check `run.state` is
   `complete` with every unit `verified`. For a combined target, continue the
   **same run_id** through Master; finalize after all declared steps verify.

A step whose profile has no worker yet is a blocker to report, never a reason
to run the step some other way. `edgar-warehouse workers describe <profile>`
says whether a profile exists.

## 3. Master

Author merge priorities in the policy by kind and field, including profile
role fields, source order, authorized clears and freshness. Use the common
Merge Stage for consolidation; field priority does not establish identity.
The implemented Rust kernels replay accepted identity decisions and rank
eligible field claims, including profile claims. Python retains policy
approval, automatic matching, profile qualification, source-history folding,
timestamps and canonical value comparisons. Contract 2 publication envelopes use
Rust object preparation from immutable database JSONB text. Contract 3
changed-record envelopes currently use SQL-built `payload_text`; stored payloads
retain their original bytes. Python checks every path against the committed hash
before sending. All
custom code stays Python; add reusable generic primitives to the Rust core.
Python also owns CLI, orchestration, integrations, retries, verification and
database clients. The database owns storage, indexed retrieval, constraints,
atomic commits, freshness/fencing, leases, durable history and recovery. The
database independently derives the commit's expected publication hash; program
preparation does not replace that authority. New executions pin the payload
adapter, facade and native binary; frozen runs retain their original runtime.
A kernel change needs parity and caller-path qualification before operational
instructions change.

Three worker profiles take parsed records into MDM; a feed's rules
file names them in its `mdm` target (or a pipeline's), after its `source.read`
step:

- `mdm.prepare`: a source extract from `source.read` into an MDM input manifest. Its
  unit's keys say which `table` of the source extract, which MDM `dataset` (source
  code) reads the rows, the `policy` digest the batches pin, the `consumer`
  they advance (its own, from checkpoint 0), a `batch_id` prefix and the
  `as_of` instant. Optional `record_column` selects an object-valued column
  containing the complete source record; omitted, the table row is the record.
  With it, optional `record_extras` names 1 to 8 other columns of the row to
  copy into the record under their own names (a flag read beside the record,
  such as a lookup reference's); absent or null adds nothing, so records
  without it are unchanged, and a name the record already holds is refused.
  Optional `distinct_on` names 1 to 8 columns of the table row: of a file's rows with equal
  values in them, only the first in file order becomes a record, so an entity
  named in many rows of one file (a counterparty listed by every filer) is one
  record of it per file. Use it when one record per row would repeat the
  entity many times over; the rows themselves belong in silver. (The Merge
  Stage has no size limit, migration 019; this is about what a record is.) Name the columns of the record key, so one kept row is one
  record; when the entity's id falls back (one id, else another), make that
  one column in the reading (`coalesce`). Rows empty in every named column
  are one key, so keep such a column filled.
  Optional `effective_column` names a column holding the file's effective
  time: an ISO 8601 instant with a timezone, written the same way in every
  row of one file and no later than `as_of` (MDM would leave later records
  out). Its publications state it, so MDM dates the records, and a link
  restated by each file starts when first stated, with `last_seen` when last
  stated. Omitted, records carry no time, and a link with no stated start
  makes no link (`unknown_relationship_start`). When the file itself states
  no such instant, take it from the caller: declare a `context` text field in
  the source extract, add the column `{context: {name: <field>}}`, and give each
  file its own context receipt ([READING.md](READING.md), "Artifact context
  and first-N rows").
  Optional `publication_key` and `revision` (text digits), together, make
  the unit's rows one publication of the caller's instead of one per file.
  With them, optional `effective_at` states that publication's time (an
  instant with a timezone, no later than `as_of`), so a later period is a
  later revision of the same records that keeps its own time; a link first
  seen in it starts then. They exclude `effective_column`.
  See [READING.md](READING.md) for shape checks. Records files of at most 1,000 rows sit beside the
  manifest. Its check reads each file against the hash the manifest states and reports `mdm.prepared`.
- `mastering.merge`: one MDM input manifest (contract version 2), merged one
  file at a time; its check reads the files back from MDM and reports
  `mdm.committed`. A reader pulls the masters changed after its checkpoint;
  nothing is published.

A unit's input names the step before it (`{"from": {"step": "read", "key": ...}}`
in a version-2 input manifest), so one run goes read → prepare → merge.

Before the first run, once per MDM database: `edgar-warehouse mdm init`. Then, for each profile in step order, as in Parse:

For an existing MDM store, before starting the new publication runtime,
rerun `edgar-warehouse mdm init --application-role <MDM application role>`
with the owner file's `DATA_URL` and `CONTROL_URL`. This applies the checksummed
publication-input schema change and preserves existing publication readers' SELECT
grants. Already frozen runs retain their original code/native binary; their
SQL claim and delivery APIs remain compatible.

For a source's target over a captured delivery, one command does steps 1–4
for every bundle and is safe to rerun: `edgar-warehouse load`
([data-operations, Load a capture](../data-operations/SKILL.md#load-a-capture)).
The steps below are what it runs, for a run you drive by hand.

1. For a combined run already submitted in Parse, retain its `run_id` and
   continue its declared steps. Otherwise submit:
   `edgar-warehouse rules run --source <name> --target <merge target> --input-manifest <uri> --input-sha256 <sha256>`.
   A source with a `dataset_contracts` section is registered in MDM first (`rules register`; `load` does it).
2. Work **each declared profile in dependency order**: `source.read`,
   `mdm.prepare`, `mastering.merge`. For example:
   `edgar-warehouse workers work mdm.prepare <run_id> --reports <uri> --limit 100`.
   For merge, source the loader file (its `DATA_URL`)
   (`MDM_APPLICATION_ROLE` names its role).
3. Repeat for each profile until its units are verified.
   `--limit 100` bounds one invocation; it does not prove the whole step ran.
4. Finish: `edgar-warehouse bookkeeping finalize <run_id>`. Done when
   `edgar-warehouse bookkeeping status <run_id>` shows the run complete and
   every declared unit verified.

A lost acknowledgement is harmless: the worker resumes the same MDM run, and
MDM never merges or publishes a batch twice. After a stop, run the same
`edgar-warehouse load` again; by hand, use `edgar-warehouse bookkeeping resume
<run_id>` and run the workers again.

## 6. Custom parsing

Only when the engine cannot state what a field needs. First check
[REFERENCE](../data-onboarding/REFERENCE.md) and the engine's primitives; a
custom step is the last resort (operator: "Write a step, then
stop").

A step is code, so it starts only after the operator says to write it: while
onboarding, write the ticket and ask first (configuration only,
[data-onboarding hard stops](../data-onboarding/SKILL.md#hard-stops)). It needs
a checkout on your own branch and is reviewed in a PR.

1. Write one plain function of one value in `edgar_warehouse/rules/steps.py`,
   registered in `STEPS` as `<name>@<version>`. It names no source or kind
   (`epoch_microseconds@1` is the reviewed-trial pattern).
2. Test it alone in `tests/engine/test_source_engine.py`: every value shape it
   accepts, and each one it refuses.
3. Call it from the feed's contract:
   `custom: {step: <name>@<version>, inputs: {value: <expression>}}`. The
   engine refuses a contract that names a step not in `STEPS`.
4. List the step in the feed's Mapping Document (the generated **Custom Parsing**
   sheet lists every custom expression and its rules path):
   `edgar-warehouse rules mapdoc write --only <source>`.
5. Run the feed's test run (Mode 4's evidence) with the step.
6. Open a PR with the step, its tests and the evidence. **Stop.** The operator
   reviews and approves the code and the rules version; never switch it on
   yourself.

### Trial evidence

`tests/engine/test_custom_parsing_trial.py` compares the generic timestamp-to-integer
step with an existing release-sequence calculation (one source's own), including negative
epochs, offsets and microseconds. It first demonstrates that the configured
`date` returns text and `number` cannot convert a timestamp. The installed-bundle
test repeats parse → prepare → merge with the custom expression and a separate
verifier. This is a review trial; no active source version names the step.

## 7. Self-check

`edgar-warehouse doctor` is the skill checking itself. When it lists an
unresolved command, either the skill text or the command line is wrong: fix
the one that is wrong, in a PR, never by guessing a replacement. The same
check runs in CI (`tests/engine/test_data_skill_bundle_postgres.py`), so a
skill cannot ship naming a command that does not exist.
