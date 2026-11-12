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

The [data-onboarding hard stops](../data-onboarding/SKILL.md#hard-stops) apply
to every mode here. In short: never approve or switch on for the operator;
never approve without a test run; never ask approval of a digest the operator cannot read; no
request to a provider the operator ruled out; never read or print a secret; no value from the data
in a public repository; never guess an identifier; never invent a command; ask one
question at a time, with your recommendation.

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
| Over-production | Building a feature, a target or a check before a source needs it | Build only what the step in hand needs |
| Defects | Guessed times, unchecked limits, a skill word CI refuses: rework | Read the clock; check bounds first; run the checks the change can affect |

**Carry a proof forward** instead of running it again: when and how is in
[mdm-engineering](../mdm-engineering/SKILL.md#choose-the-cheapest-proof),
"Choose the cheapest proof", its last row.

## Guide the task to completion

For readiness, cross-reference mapping/lookup, missing proof, draft-to-final
work, deployment or activation, follow [Completion guide](COMPLETION.md) first.
Explain the observed state per selected engine, give the ordered remaining steps and keep the task's
checklist current while carrying them out through the owning skills. Return to
that checklist after each handoff; naming an owner alone does not finish a step.

A request to create qualification evidence starts from the available draft and
retained inputs. Discover those inputs and generate the proof from the run;
an existing final release is not a prerequisite for creating one. Reuse genuine
matching evidence and authorization already given. Present a concrete tested
version before requesting its approval, and continue independent authorized work
while a necessary input or approval is pending.

For catalog restoration, Mapping Documents, entity domains, glossaries, quality
publication, unclear asset names or coverage of all entities/pipelines, use
[Business catalog](../data-onboarding/CATALOG.md).
This is configuration metadata publication; source processing and activation
retain their own gates.

## Source readiness

When running, recovering or qualifying a source, apply these operator requirements. They are acceptance rules; identify missing runtime enforcement as
an implementation gap before calling a source ready.

- Qualify retained local captures through genuine provenance, completeness
  evidence and the normal Rules lifecycle. Local processing qualification can
  precede AWS capture qualification. Provider requests retain their separate
  authorization; missing evidence blocks affected processing.
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
| Start | Explain current state and complete the remaining steps | [Completion guide](COMPLETION.md) |
| 0 | Setup, once per machine | this file |
| 1 | Onboard a new feed or kind | [data-onboarding](../data-onboarding/SKILL.md) |
| 1b | Change a live feed's rules | [refining-rules](../refining-rules/SKILL.md) |
| 2 | Parse: read captured files with the configured engine | this file, then [bookkeeping RUN](../bookkeeping/RUN.md) |
| 2b | Combine keyed collections and join configured source extracts | [COMBINING.md](COMBINING.md) |
| 3 | Master: the parsed records into MDM | this file |
| 4 | Approve and switch on | [APPROVE](../data-onboarding/APPROVE.md) |
| 5 | Recover a run | [bookkeeping RECOVERY](../bookkeeping/RECOVERY.md), [change-journal](../change-journal/SKILL.md) |
| 6 | Custom parsing, only when the engine cannot state a field | this file |
| 7 | Self-check | this file |

## Connection URLs and environment

This is the sole skill section for service URLs and connection setup. Other
skills link here; they retain their operational procedures, not copies of
the connection instructions.

### Discover existing configuration first

Check variable presence without displaying values in the process environment,
the active worktree's root `.env`, and the shared
`~/.local/share/edgartools/.env` before asking for a connection. A worktree
does not automatically inherit another worktree's ignored `.env`. Confirm the
requested environment and duty before using any saved address; a discovered
URL does not authorize a different target.

Keep private files mode `0600`, outside Git or covered by its ignore rules.
Load only the selected variables into the process that needs them, without
shell tracing or printing the file. Source only trusted, operator-controlled
shell env files; parse dotenv files as data when they are not shell-compatible.
Keep existing explicit process values unless deliberately selecting a new
environment. Missing configuration means ask the operator to set it in their
own terminal, never paste it into chat. Examples contain placeholders only.

The shared `.env` is a private URL catalog across agent worktrees. Standard
database variable names hold hosted worker connections. Saved alternatives
use `HOSTED_PROD_VERIFIER_`, `HOSTED_PROD_GOVERNANCE_`,
`HOSTED_PROD_CONNECTION_` and `WORKTREE_` prefixes. These are catalog aliases,
not variables applications automatically select. Preserve the original role
files and refresh saved values from them when connections change; do not
combine credentials or silently substitute an owner for a runtime login.

### Database connections and duties

Each store uses its own database and URL; never derive another store's URL
by changing an MDM address. Preserve the complete authorized dialect, host,
port, database, role, credential and SSL options.

Bare PostgreSQL and MySQL URLs select the shipped drivers. An independent
Bookkeeping installation needs its `mysql` extra for MySQL; an independent
Change Journal installation needs its selected `mysql` or `sqlserver` extra.
Provision separate owners and restricted runtime roles, retaining the
environment's ownership checks; do not adopt another workstream's databases.
Missing store configuration never falls back to a legacy store, another
store's URL, or a guessed database name.

| Store | Runtime variable | Migration/owner variable |
|---|---|---|
| MDM | `MDM_DATABASE_URL` | `MDM_MIGRATION_DATABASE_URL` |
| RDM | `RDM_DATABASE_URL` | `RDM_MIGRATION_DATABASE_URL` |
| Rules | `RULES_DATABASE_URL` | `RULES_MIGRATION_DATABASE_URL` |
| Bookkeeping | `BOOKKEEPING_DATABASE_URL` | `BOOKKEEPING_MIGRATION_DATABASE_URL` |
| Change Journal | `CHANGE_JOURNAL_DATABASE_URL` | `CHANGE_JOURNAL_MIGRATION_DATABASE_URL` |
| Silver | `SILVER_DATABASE_URL` | `SILVER_MIGRATION_DATABASE_URL` |

The selected stores folder is authoritative: use its `worker.env` for work,
`verifier.env` for independent verification, `connection.env` for owner or
migration duties, and `governance.env` for activation. Source the appropriate
trusted file in a command-scoped subshell with `set -a` and disable tracing.
`load --stores` takes this folder and selects duties itself, not a single
`.env` file. `infra/scripts/local-test-stores.py` creates local role files.

MDM and Bookkeeping migration commands consume their ordinary
`*_DATABASE_URL` variable as the owner for that command only; other stores'
migrations consume `*_MIGRATION_DATABASE_URL`. Never leave owner connections
as runtime defaults. Activation additionally needs
`RULES_MDM_ACTIVATION_DATABASE_URL` from the governance file; destination
guard setup uses `DESTINATION_MIGRATION_DATABASE_URL` as its owner.
`PROFILE_DATABASE_URL` is a separately authorized profiling login with access
to database activity. Configure these only for their requested duty.
For load profiling, `quality` reads MDM, `progress`, `failures` and `steps`
read Bookkeeping, and `sample` uses the profiling login's `pg_stat_activity`
access.

Rules commands use the restricted `rules_agent` login; activation uses the
Rules governance login plus the MDM governance connection. Silver landing
uses its runtime connection and the MDM runtime connection to resolve master
IDs. Bookkeeping work and verification must use different authenticated
logins; each profile grants worker duty to `bookkeeping_runtime` and
verifier duty to `bookkeeping_verifier`, never both duties to one login.
For a hosted store, both are members of `bookkeeping_control`, the group
role passed to Bookkeeping initialization/migration. MDM verification uses
`mdm_verifier` with schema usage and read access to prepared/mastering tables.
The application guard uses runtime role `mdm_runtime`.

When provisioning these files, use `umask 077`, retain TLS settings
(`sslmode=require` for the hosted PostgreSQL target), and keep owners
separate from restricted runtime logins. `mdm_governance` needs database
`CONNECT`, schema `USAGE`, read access to prepared/mastering tables, and
`INSERT` on `mdm.policy`, `mdm.dataset` and `mdm.dataset_mapping`, plus the
registration grant. `rules_governance` needs Rules agent and approver
membership. Apply the committed provisioning and grant procedures rather
than granting administrative rights to runtimes.

`MDM_APPLICATION_ROLE` names the application role.
`BOOKKEEPING_MANIFEST_ROOT` is the manifest folder written as a `file://`
URI (a plain path is refused), or the authorized S3 prefix on AWS. The role
files carry these non-URL settings too; a URL-only catalog does not replace
them. Check configuration with `edgar-warehouse doctor`, then the requested
read-only connectivity command; report presence and outcomes, not addresses.

### Snowflake and catalog services

Snowflake SQL uses the explicit named connection `edgartools-prod`; inspect
connection names in `~/.snowflake/connections.toml` and defaults in
`~/.snowflake/config.toml` without displaying credentials. Do not derive a
connection name from the environment slug. `snowconn` is decommissioned.
For dbt, retain the selected private profile or its configured
`DBT_SNOWFLAKE_ACCOUNT`, `DBT_SNOWFLAKE_USER`, `DBT_SNOWFLAKE_PASSWORD` and
`DBT_SNOWFLAKE_WAREHOUSE` values. Select the production target explicitly;
do not inherit retired development defaults or copy credentials into examples.

Snowflake-hosted MDM is PostgreSQL protocol on port `5432`, not the Snowflake
SQL connection. Its complete authorized DSN belongs in private `.env` storage.
Do not infer it from the SQL account, rotate access to discover it, or run a
bootstrap/reset command as a URL lookup. Graph analytics lives inside
Snowflake; there is no external `NEO4J_URI` or Bolt endpoint.

OpenMetadata uses `OPENMETADATA_URL` and `OPENMETADATA_TOKEN`, an authorized
bot token from private configuration. The local server endpoint is
`http://127.0.0.1:8585`; confirm the configured instance rather than replacing
it with that default. Retain the token privately; login/token creation and
catalog operations belong to the OpenMetadata skill.
The server root has no `/api/v1` suffix when passed to `catalog.connect`,
which appends it. Local initialization may instead use
`OPENMETADATA_LOGIN_EMAIL` with `OPENMETADATA_LOGIN_PASSWORD` (or the
supported `OPENMETADATA_PASSWORD` alias) for native login.

## 0. Setup

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
   capabilities with [data-operations](../data-operations/SKILL.md#apply-store-ddl).

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
   and `silver`. Do not paste the statement or an address into the chat. Do
   not apply the store schemas here.
   [data-operations](../data-operations/SKILL.md) applies that DDL into these
   databases. Use [Connection URLs and environment](#connection-urls-and-environment)
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

1. The feed's pipeline is saved, tested, approved and switched on (Mode 4).
2. Submit: `edgar-warehouse rules run --pipeline <name> --target <target> --input-manifest <uri> --input-sha256 <sha256>`.
   Keep the `run_id` it prints.
3. Work, as the worker login: `edgar-warehouse workers work source.read <run_id> --limit 100`.
4. Verify, as the verifier login (a different `BOOKKEEPING_DATABASE_URL`):
   `edgar-warehouse workers verify source.read <run_id> --reports <uri> --limit 100`.
5. Repeat work and verify until every read unit is verified; the limit bounds
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
Future kernel migrations require parity and caller-path qualification before
changing operational instructions; this slice does not change approval or
activation steps.

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
  manifest. Its verifier rebuilds them and reports `mdm.prepared`.
- `mastering.merge`: one MDM input manifest (contract version 2), merged one
  file at a time; its verifier reads the files back from MDM and reports
  `mdm.committed`. A reader pulls the masters changed after its checkpoint;
  nothing is published.

A unit's input names the step before it (`{"from": {"step": "read", "key": ...}}`
in a version-2 input manifest), so one run goes read → prepare → merge.

Before the first run, once per MDM database: `edgar-warehouse mdm migrate`,
then `edgar-warehouse bookkeeping init-guard --runtime-role <MDM application role>`
with `DESTINATION_MIGRATION_DATABASE_URL` set to the MDM database's owner,
since every MDM commit is checked against the worker's live lease. Then, for each profile in step order, as in Parse:

For an existing MDM store, before starting the new publication runtime,
rerun `edgar-warehouse mdm migrate --application-role <MDM application role>`
with the migration owner's `MDM_DATABASE_URL`. This applies the checksummed
publication-input migration and preserves existing publication readers' SELECT
grants. Already frozen runs retain their original code/native binary; their
SQL claim and delivery APIs remain compatible.

For a source's target over a captured delivery, one command does steps 1–4
for every bundle and is safe to rerun: `edgar-warehouse load`
([data-operations, Load a capture](../data-operations/SKILL.md#load-a-capture)).
The steps below are what it runs, for a run you drive by hand.

1. For a combined run already submitted in Parse, retain its `run_id` and
   continue its declared steps. Otherwise submit:
   `edgar-warehouse rules run --source <name> --target <merge target> --input-manifest <uri> --input-sha256 <sha256>`.
   A source with a `dataset_contracts` section needs the operator's approval of that rules version first (Mode 4).
2. Work and verify **each declared profile in dependency order**: `source.read`,
   `mdm.prepare`, `mastering.merge`. For example:
   `edgar-warehouse workers work mdm.prepare <run_id> --limit 100`, then
   `edgar-warehouse workers verify mdm.prepare <run_id> --reports <uri> --limit 100`.
   Use the worker Bookkeeping login for work and the separate verifier login
   for verify. For merge, set `MDM_DATABASE_URL` to the MDM
   application login for work (`MDM_APPLICATION_ROLE` names its role), and to
   the separate MDM verifier login for verify.
3. Repeat work and verify for each profile until its units are verified.
   `--limit 100` bounds one invocation; it does not prove the whole step ran.
4. Finish: `edgar-warehouse bookkeeping finalize <run_id>`. Done when
   `edgar-warehouse bookkeeping status <run_id>` shows the run complete and
   every declared unit verified.

A lost acknowledgement is harmless: the worker resumes the same MDM run, and
MDM never merges or publishes a batch twice. After a stop, run the same
`edgar-warehouse load` again; by hand, use `edgar-warehouse bookkeeping resume
<run_id>` and run the workers again.

### Examples: current source qualification

Company's last installed proof (a killed worker
resumed, a second pass changed nothing) and
Person's installed trial are the evidence their versions carry forward. Use
only pipelines whose every profile resolves with `workers describe`.

## 6. Custom parsing

Only when the engine cannot state what a field needs. First check
[REFERENCE](../data-onboarding/REFERENCE.md) and the engine's primitives; a
custom step is the last resort (operator: "Write a step, then
stop").

This mode needs a checkout of the repository on your own branch, since a step
is code reviewed in a PR.

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
