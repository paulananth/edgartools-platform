# Edgar Intelligence runbook: initialize

A hosted store initialized from nothing, then its first load of every captured source, and the dependencies between loads. Index: [README](README.md).

## Initialize a hosted store

A hosted PostgreSQL 16 instance (Snowflake Postgres) is initialized with the same commands as the local store, in this
order, by skills and their own commands only. Use
[Connection URLs and environment](../../../skills/data-platform/SKILL.md#connection-urls-and-environment) for the private connection
files, roles and credential handling. The commands below are the whole procedure; each prints names and checksums, never
a connection value.

**Run every step, 1 to 9, in order, and say which ran.** The readiness gate (step 9) reads the result of steps 2b to 8 (steps 5 to 7 by its
`REGISTERED` check) but does not run them: a store reset and given its schemas, with the registration, rules and worker grants skipped, passed an
earlier gate, and every load step then stopped within seconds at "permission denied for schema mdm".

The stores folder is `~/.config/edgartools/hosted/`, one folder for the store: `owner.env` (the owner login, `DATA_URL` and `CONTROL_URL`),
`worker.env` (the runtime logins and the manifest root), `governance.env` (the registration login). `load --stores`
takes it. A second copy of these files elsewhere goes stale, and a stale copy fails `doctor` with a login error.

1. **Instance.** [aws-snowflake-operations](../../../skills/aws-snowflake-operations/SKILL.md) creates it (snowflake-postgres skill,
   `pg_connect.py --create`; its comment takes letters and spaces, a `;` is refused). Wait for `state` to read `READY`,
   then for its hostname to resolve on this machine. A lookup made before the name existed can stay cached as "not
   found" for up to an hour while a public resolver already answers (`dig +short @8.8.8.8 <host>`, count the lines,
   never print them): the operator flushes the cache (`sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder`
   on macOS). A rotation of a login's password needs the operator's word, and nothing below needs one.
   Run every command below from a checkout of today's `main` with its environment built
   (`uv sync --extra mdm --extra s3`) or a bundle installed from it: an older `edgar-warehouse`
   creates older schemas.
1a. **Quiesce and drain (before step 2).** Before resetting an existing instance, stop scheduled
   loads and applications that can reconnect to its databases. Check
   `load_chain.py --status` and Bookkeeping's open runs and leases; all must be
   clear. Inventory managed mirrors with the Snowflake Postgres mirror skill.
   Resolve any mirror that reads a database being reset through that skill's
   approved drop or restart procedure first; approval to reset the hosted
   stores does not authorize a mirror operation.

   Once clients are stopped, use the Snowflake Postgres management skill and
   the configured production instance to restart PostgreSQL:
   `snow sql --connection edgartools-prod -q "ALTER POSTGRES INSTANCE <instance> RESTART POSTGRES"`.
   This disconnects existing sessions; wait for the instance to return to
   `READY`, reading only its name and state from the instance description. Then
   run the read-only reset preflight below. Continue only when no client
   session or active transaction remains. Snowflake-managed `pg_lake` workers
   can return after restart; the script reports idle extension workers without
   transactions separately and the approved database drop disconnects them
   with `WITH (FORCE)`. If any client session or extension worker with an open
   transaction remains, stop. Never terminate internal sessions directly or
   bypass the reset script's session classification. The service restart is
   disruptive and needs the operator's approval; approval to reset the
   databases alone is not approval to disconnect every client.

2. **Databases.** An instance that holds an old store keeps its logins and gets its databases made again: with the
   operator's word, list them, then drop and create them with the owner and the grants each had:
   ```bash
   set -a; . ~/.config/edgartools/hosted/owner.env; set +a
   python infra/scripts/reset-hosted-databases.py             # lists sizes and session classes; drops nothing
   python infra/scripts/reset-hosted-databases.py --words "<the operator's exact words>"   # refuses client sessions/transactions; records any forced idle-worker disconnects
   ```
   The drop also deletes the dropped stores' run files (`<manifest root>/load`, the root `worker.env` names): no store refers
   to them once Bookkeeping is dropped. Extracts (`<manifest root>/extracts`) stay, since a load reuses one by its content. A
   load deletes each bundle's files once its run is verified, so only a run that stopped keeps files, to resume.
   A fresh instance gets its two databases (`data`: mdm, rdm and silver; `control`: rules, bookkeeping and the change journal,
   each store a schema) and their restricted logins from the stores folder's own files, each login with the password its URL already holds (no login
   is rotated; the first confirmed run also makes the diagnostic login `ops_reader`, with `pg_monitor` and no store, and its
   `reader.env`). Each login gets CONNECT on its databases, never TEMPORARY, and PUBLIC gets nothing: no load creates a
   table, temporary or not. Every URL then
   names the new instance, and the administrator's URLs its new password:
   ```bash
   python <data-platform skill>/scripts/provision_hosted_store.py --service <the instance's saved service>            # lists
   python <data-platform skill>/scripts/provision_hosted_store.py --service <the instance's saved service> --confirm
   ```
   Every load uses one login, `edgar_loader`, which can create nothing: add `--loader` (with `--confirm`) and every
   runtime URL in `worker.env` names it (the old file is kept as `worker.env.before-loader`). It is a member of the six
   runtime roles, so it holds exactly their privileges, and the command refuses it if it could create in any schema of any
   store, owns an object, or is a superuser or can create databases or roles. A store's schema is made and changed by its
   owner login in step 3, never by a load. With `--loader` every runtime URL in the stores folder names it, and `--retire` (with `--confirm`) then makes the six runtime logins
   NOLOGIN groups; the loader keeps its privileges through its membership. NOLOGIN stops new logins and ends no open session: the command
   refuses, leaving each role a login, while a URL still names one or a session is logged in as one, so run it after a load that started
   under them ends.
   The service is the one the instance's creation saved (snowflake-postgres skill, `pg_connect.py --create`). Wait for
   its hostname to resolve first. Done when the second run prints that every URL names the new instance.
2b. **Role guards.** With `owner.env` sourced, `python infra/scripts/harden-hosted-roles.py` lists what each login lacks, and `--confirm` applies it:
   a connection limit per login, statement and idle-transaction timeouts, a `work_mem` ceiling for the loader and the audit classes
   for the logins that change schemas, policy or approvals. Done when it prints that every login role holds its guards. The guards belong to
   the roles, which a reset of the databases keeps, so the step is safe to run again. Read [HOSTED-LOADS.md](../../../skills/data-operations/HOSTED-LOADS.md) before a load.
3. **Schemas** (data-platform's step, [STORES.md](../../../skills/data-platform/STORES.md)), each by the owner login, in one shell that holds `owner.env`. Each command finds its store's database by its group: `DATA_URL` for mdm, rdm and silver, `CONTROL_URL` for rules, bookkeeping and the change journal:
   ```bash
   edgar-warehouse mdm init --application-role mdm_runtime
   edgar-warehouse rdm init --runtime-role rdm_runtime
   edgar-warehouse bookkeeping init --runtime-role bookkeeping_control
   edgar-warehouse change-journal init --runtime-role change_journal_runtime
   edgar-warehouse silver init --runtime-role silver_runtime
   edgar-warehouse rules init --agent-role rules_agent
   ```
   `init` is the whole step, on a fresh store and again when a later schema file arrives. Done when
   each prints its schema file's checksum. RDM's `init` also creates `rdm.published_code`, the codes of each code set's one published version as a table
   for the mirror; `rdm.published_code` is filled each time a version is published (step 4 publishes them), never edited.
4. **RDM codes.** With `worker.env` sourced, `python <data-operations skill>/scripts/rdm_restore_published.py`
   (no approval is asked: the operator's standing ruling, 2026-11-19, is in the approval record, under an approver other than the drafter, since the store refuses a self-approval).
   A half-restored RDM cannot be edited (published and approved versions are guarded): drop the `rdm` schema as its owner and run `rdm init` again.
   Run it once: a second run is refused at its first insert, since every version exists, and changes nothing; to check, count `rdm.code_set_version` (one per pin) and `rdm.published_code`. Done when every pin reads `pin ok` and
   `SELECT count(*) FROM rdm.published_code` equals the codes of the published versions.
5. **Registration login.** With `owner.env` sourced, `edgar-warehouse rules init` (its `--registrar-role`, `rules_governance`, may add to
   the registry, `rules.policy` and `rules.dataset_reading`, and nothing else; the loader's role reads it).
6. **Source configurations.** `edgar-warehouse rules check` (every source, offline), then, with `governance.env`
   sourced, `edgar-warehouse rules register`. Done when it prints a digest for the merge rules and every Dataset Contract.
   Then the silver tables (data-platform's step; a load creates none and stops when one is missing):
   `bash infra/scripts/deploy-silver.sh ~/.config/edgartools/hosted/owner.env`.
   A table whose spec was redesigned stops it with "holds another spec": as the owner, `DROP TABLE silver.<table>` and
   `DELETE FROM silver.table_spec WHERE table_name = '<table>'`, then run it again (the loads rebuild the rows).
7. **Worker grants**, with `owner.env` sourced, one per worker profile:
   ```bash
   for p in $(python -c "from edgar_warehouse.workers import PROFILES; print(*PROFILES)"); do
     edgar-warehouse bookkeeping grant-profile --profile "$p" --worker bookkeeping_runtime
   done
   ```
   Done when `doctor` prints `"ok": true` under `worker.env` (it checks MDM, Rules, Bookkeeping and the Change Journal; steps
   4 and 6 prove RDM and Silver) and `load --plan` reads a capture.
8. **Catalog.** A catalog (the [openmetadata skill](../../../skills/openmetadata/SKILL.md)) describes the rules, so a reset of the stores
   changes none of it, but its text may have moved since it was last published. With the catalog's private file sourced:
   `edgar-warehouse rules catalog --root rules publish`, then `... check`. Done when `check` prints `confirmed` with no differences.
   The statuses it already holds for the steps are the previous load's history; the new load's statuses supersede them (see
   [data-operations](../../../skills/data-operations/SKILL.md#publish-a-steps-status-to-the-catalog)).

9. **Ready.** `python <data-operations skill>/scripts/readiness.py` reads the infrastructure and writes `readiness.json` only when every check passes (code with green CI, engine built from this source, `doctor`, guards, reference data, captures, quiet instance, room, audit, each duty file's login, the chain's state file, the catalog). Done when it prints `READY` (thirteen checks, the last `REGISTERED`: the merge policy, the Dataset Contracts and every worker profile). The gate is not this runbook: say which steps ran and which did not before a load starts. A load does not start without it, and any reset of the databases or new commit closes it again.

A missing grant or login that a command names is a gap to fix through the central connection section, not to work around.

## Load a fresh store

`rules/load-chain.yaml` holds the order of every source and target, each one's input (its source names the folder in `sources/<source>/inputs.yaml`), workers and the facts and revision no capture states, and
`scripts/load_chain.py` runs it, so a store is loaded the same way every time and nobody rewrites the list:

A load runs only in the loader image CI built from `main`, started by `infra/load-pipeline/load.sh [--plan] [--finish] <step>...`
(data-operations, HOSTED-LOADS.md, "Where a load runs"). In a checkout `load_chain.py` reads (`--plan`, `--list`, `--status`) and
refuses to start, resume or finish a load. The commands below are what the image's worker runs:

```bash
python <data-operations skill>/scripts/load_chain.py --plan     # documents and bundles per step; writes nothing
python <data-operations skill>/scripts/load_chain.py --auto      # watch the loads; start each step when its lane is free
python <data-operations skill>/scripts/load_chain.py            # one process, the steps in file order; stays awake
python <data-operations skill>/scripts/load_chain.py --from <step>   # carry on; a step that is done costs one call
```

**`--auto` is the way to load a store.** It starts the step at the head of every lane whose dependencies are done, longest
first, while a slot is free (`--slots`, by default half the machine's gigabytes, at most its cores, at least two) and the machine has
headroom (a load average under one and a half times the cores, and memory not short: swap over three quarters used counts only while less than a quarter of memory is free, since the system keeps swap long after the load that filled it; under a tenth of memory free presses on its own, and an unreadable memory counts as short); it also reads the database as the reader login (a step starts only while fewer than three sessions wait on locks, none for a minute, and
less than four fifths of its connections are in use), and it starts one step a
cycle, since the load average lags. It moves each running step's workers within its capacity profile's range (`--capacity`) by the readings: a step is raised at most once in ten minutes, counted from its start or its last move (a move stops its load and starts it again, abandoning the bundles in flight), while a pressed machine sheds the step with the shortest chain at once: the step with the
longest chain behind it doubles when there is room, and the step with the shortest halves when the machine or the
database is pressed, by stopping its load and starting it again (a load resumes where it stopped). Priorities and the projected end use each step's measured minutes (its first start to its `done` line) where it has run, and
an estimate where it has not: its bound times the share of its bound the done steps used. A running step that outruns its
estimate has disproved it, and the projection then counts its bound, so it is an upper bound, never a promise. The
scheduler aims for `--connections N` database connections (250 by default): workers rise while fewer are in use and the
machine has room, and it says when the machine, not the database, is the limit; to use more connections, run the loaders
on more compute (production runs them on AWS). With `--hours H` or
`--deadline HH:MM ET` the run is held to that schedule: a run behind it is allowed twice the cores in load, and at the
deadline the miss is reported once, naming what is left, while every load goes on (a deadline never stops one; the run says how long
after it the last step finished). A step that uses up its attempts blocks its lane and whatever waits for it; the
rest carry on, and the scheduler stops, naming what cannot start, when nothing else can. Every step runs as
`load_chain.py --only <step>`, so the attempts and the one-load-of-a-source-and-target rule are the same as by hand.

**A fresh store starts a fresh state file, and a run label can be used again.** The chain's `done` lines are read from
`chain-<RUN>.log`, which names the store it belongs to: its instance (by the address, never shown) and its database's creation
identity, so a store whose databases were made again is another store even at the same address. A run whose file was written for
another store, another generation of this one, or no store at all (an old run's file, from before markers, under a label used
again) sets it aside beside it (`chain-<RUN>.log.<store>`, `.<store>-<generation>`, `.unmarked`; never deleted, never overwritten) and starts a fresh one,
so an earlier load's lines never satisfy a wait and never stop a run. A generation that cannot be read changes nothing, and a file written without one (from before generations, or while it was unreadable) is trusted and learns it the next time it can be read; only from then is a reset of the stores caught for that file, so a label used again right after a reset should be a new one when the file is older than the generations. `--status` prints when the next run would set the file aside, and does not count its done lines.
`--adopt-state` is for the operator who says an unmarked file is this store's and keeps it.

A fresh store takes hours, and the shape is the same each time. The longest step is the GLEIF merge, which holds the mastering lease, so a step that
writes silver for the same masters shows no CPU, no session and no rows until that merge ends, then runs at once: `--status` says "no sign of work"
for it, and the log of a step with one document stays silent. That is a wait, not a stall; read the leases (below) before stopping anything. The finish
(`--finish`) follows the last step and builds the links tables and `master_binding` whole from the stored records; no silver row is rewritten.

Masters come first and each source's silver target last, so silver rows find their masters as they land; a silver step
needs none before it (a row lands with its link key and finds its master by a join on `master_binding`, which `--finish` builds). A source's later
delivery is a new publication and carries the next `--revision`. The chain stops at the first step that does not finish
in its attempts and names why in that step's log. After the last step it builds the links tables and `master_binding` once (`--finish` runs only those; the
name-search lookups are built only on `--finish --lookups`, since a load reads none of them and only the context search does). Check a running chain every 30 minutes; a step that stops reports at its
check, never on a tighter loop.

### The links tables and `master_binding` are built once

The links tables and `master_binding` (each source key's master) are built whole from every stored record
(`edgar-warehouse silver links`), so no target carries a step for them. No master id is written on a silver row. A `load` run alone builds it after its last bundle when it mastered anything; a load that is one of several
passes `--no-links` and the last step builds it (the chain's `--finish`). A newly mastered record can be the end a
stored link waited for, so any load that masters builds, whatever its source states.

### Dependencies between loads

Loads depend on each other only as the rules say, and `python <data-operations skill>/scripts/infer_dependencies.py` prints it from
the rules files: nothing here comes from a machine's size. No source needs another loaded first: the Merge Stage holds a
record that finds no master and releases it when a later file gives one, so a load that runs early is never wrong. The
rules state three kinds of ordering:

- **Must** (a load leaves something out otherwise). A target that publishes a second batch of its source's records follows the
  target that publishes the first. The links tables and `master_binding` follow every load (`--finish`).
- **Prefer** (records wait until the other load is done; never wrong, only later). A source with a
  matching rule that waits follows the source the rule names (`holder_source`), else the sources whose minting rules use the
  same identifier namespace, else the sources that mint its kind. Links set no order. Two sources that each prefer the
  other have no order to keep.
- **Alone** (these take turns; they are not dependencies). Merges of one kind of master data that merge golden records or create them by exact name (one that joins stored ones, or creates by an identifier, runs beside the others), and two loads of one source and target (their outputs would collide).

Everything else runs at the same time. The chain file turns that into lanes: `lane` marks steps that may run together,
`waits_for` is the edges above that cross lanes, and tests hold every wait to an inferred edge and every inferred edge to a
wait or an earlier step of its lane, so a rule change that adds a dependency fails a test until the chain follows it.

By hand, instead of `--auto`:

```bash
for lane in A P S C L O D F G N Q; do python <data-operations skill>/scripts/load_chain.py --lane $lane & done   # eleven lanes, one process each
python <data-operations skill>/scripts/load_chain.py --finish          # once every lane reports its last step done
```

A step waits for the steps of other lanes it needs, and for any other load of its own source and target to end.

#### Fit the whole load into the window

The window is met by the longest chain of steps that must follow one another, never by the sum of the steps. Plan it from
the rules, not from a lane's habit:

1. Print the edges: `python <data-operations skill>/scripts/infer_dependencies.py`. A step with no edge to a step still
   to run starts at once.
2. Give a step its own lane when nothing it waits for is in its lane's earlier steps. A lane is a queue: a long step
   behind another in one lane waits for it even when the rules say it need not (GLEIF joins only the SEC Company masters,
   so it has a lane of its own and starts when those are done).
3. Keep steps in one lane only when they must take turns (merges of one kind of master data that join stored records,
   or two loads of one source and target) or when each is too short to matter.
4. Order a lane's steps by what must follow, and start every lane at once. `--auto` starts first the ready step whose own
   `minutes` plus the longest chain of steps that follow it is largest.
5. Read the critical path from the logs, not the plan: the step still running when every other lane is done sets the
   total. If it is not the step the plan named, a step waited for something the rules do not state; fix the chain file
   and its test (`tests/unit/test_load_chain.py` holds each wait equal to the inference), then the lane.
6. Machine size sets how many lanes run well at once, not their order (see daily run, "Resource sizing"). Memory in
   use beyond the machine's, shown by short memory (swap used while little is free) and a load average above the cores, slows every lane: add lanes when the
   running ones leave memory free, and start the longest first.

**`--plan` proves the documents, not the rest.** It counts what each step would read; it does not open a file a step reads
beside its capture, and it does not write, so it cannot find a missing right. A fresh store's first minutes find them:
a lane stops when its step uses up its attempts (the chain file sets them for each step) and names the step. Read its reason where the step's log points, the stores folder's
`load-errors.log` (one file for every lane, rotated at 10 MiB into `load-errors.log.1` and gzipped `.2.gz` to `.5.gz`: find the step's own command and its last lines), fix the cause, and run the
lane again; a step that is done costs one call. A silver step that reports "a value is not its column's type or a storage
constraint refused the delivery" now adds the database's SQLSTATE and the constraint or column it names; a SQLSTATE
42501 is a missing right, not a value.

#### Files a load needs beside its capture

Some sources read a second file kept in their own capture folder, which no other load supplies. Such a load is **Needs**: it
stops until the file is there, and the lane that holds it stops with the reason above. The chain file's steps for
these sources name the file by its fact (`facts`); the file is an additive copy of one already on this machine, with its
receipt (the file, its bytes and its sha256), never a provider request.

| Source | File | Where it comes from |
|---|---|---|
| OpenFIGI (every capture folder it loads) | the SEC's `company_tickers_exchange` file dated the step's `ticker_file_date` fact (the rules read whichever file is there and stamp that fact on the rows, so the date is the operator's to keep right) | the SEC Company capture that retained it (`bronze/reference/sec/company_tickers_exchange/<year>/<month>/<day>/`); copy it to `company_tickers_exchange/<year>/<month>/<day>/company_tickers_exchange.json` in the OpenFIGI capture folder, check its sha256 against the Company capture's receipt, and append its receipt line to the folder's `receipts.jsonl` |

#### Examples: this store's dependencies

From the shipped rules: no source is a must for another, and a source that only finds (never mints) is GLEIF, which
follows the SEC Company masters its rule names. The links table is built by the N-PORT fund, N-PORT security, N-CEN
fund, N-CEN class and GLEIF targets, and its contracts are stated by those and by Form ADV and ownership, so GLEIF, the
last build, follows Form ADV and ownership. Form ADV follows the Company registrants (SEC Company, N-PORT and N-CEN),
ownership follows SEC Company, and ownership's ticker symbols follow OpenFIGI, 13F and N-PORT securities. OpenFIGI,
13F securities and N-PORT security each prefer the others: either order. SEC persons, the silver-only sources and each
quarter's N-CEN registrants and advisers have nothing to follow, so they start at once.

## Load priority

When several steps can start at once, `load_chain.py --auto` starts them in the order of the chain file's `priority`, then the longest
chain behind a step (its own time plus the longest run of steps waiting on it, by measured times). A priority orders only what is ready:
a step still waits for its lane and its `waits_for`. The rule that sets a tier, and the measured chain that placed each step in it
from the first full load, so a change of tier is a change of evidence (edit `priority` in `rules/load-chain.yaml`; a test holds this
table to that file):

| Priority | Steps | Why |
|---|---|---|
| 1 | `13f-filings`, `registration`, `ipo`, `company`, `nport-security`, `gleif-pairs`, `gleif`, `openfigi-answers` | The critical path: 100 minutes or more of chain behind each (measured: 242, 222, 214, 162, 147, 135, 134 and 111). `13f-filings` and `registration` are short but hold `ipo` (the longest step) behind them in their lane; `company` and `gleif-pairs` hold GLEIF behind them |
| 2 | `company-facts`, `nport-security-silver`, `person` | 30 to under 100 minutes of chain (measured: 90, 90 and 50): long, but nothing waits on them |
| 3 | every other step | Under 30 minutes of chain (the longest measured: 28) |

Every other step is priority 3, and a step added without a `priority` is priority 3. Measure again after a load that changed the
critical path (`load_chain.py --status` shows each step's progress and `chain-<RUN>.log` its time) and move a step only on that evidence.

## Mirror the final tables

After the load (and `--finish`), one Snowflake mirror of the data database carries the final tables: the tables named in `sources/managed-mirror.yaml`, each of
which `destination/authorised_data_sharing.yaml` lets leave the stores. Its schemas are `MDM`, `RDM` and `SILVER` (the source schema's name in upper case), and
its target database is `mirror.database` in `rules/snowflake.yaml`. The procedure, its read-only checks and its approval (one create plan) are
[the data-platform skill's hosted mirroring guide](../../../skills/data-platform/HOSTED-MIRRORING.md#after-the-first-load-mirror-only-the-exposed-subset).
Done when `mirror_sql.py readback --listing <the listing as JSON>` passes: the mirror lists exactly its recorded tables, each replicating, in schemas `MDM`, `RDM` and `SILVER`, with none missing or unexpected.
`--finish` writes `finish took <n> min` to the chain's state file (the bound is five minutes without lookups): record that figure on the ticket.

The mirror is made, in this order, after `--finish`: (1) `exposure_manifest.py generate`, then `check` (read-only); (2) the guide's read-only pre-flight on the data
database (instance `STANDARD_*` or `HIGHMEM_*`, a key and a supported type on every column) and `mirror_sql.py exists`, which must show the target absent before a
create; (3) `mirror_sql.py plan`, approved by the operator before any `CREATE_MIRROR` (billable), then `mirror_sql.py create`. The target is Iceberg on
Snowflake-managed storage with serverless apply. A target name cannot be reused, so a mirror that is dropped and made again takes a new name.

The Snowflake database names are in `rules/snowflake.yaml`, nowhere else. A target database cannot be renamed, and while its mirror replicates the Snowflake application owns it (the owner role can own it only after `DROP_MIRROR(<mirror>, FALSE)`, [HOSTED-MIRRORING](../../../skills/data-platform/HOSTED-MIRRORING.md)), so a new
name means a new mirror: create it beside the old one, wait until every table reads `REPLICATING` with equal counts, change the name in
`rules/snowflake.yaml`, then `DROP_MIRROR(<old mirror>, TRUE)` ([HOSTED-MIRRORING](../../../skills/data-platform/HOSTED-MIRRORING.md)).

A store **reset** (step 2) breaks a mirror: the guide says what to plan first. Before a reset, list the mirrors (`SHOW DATABASES LIKE '%MIRROR%'`, read-only).
