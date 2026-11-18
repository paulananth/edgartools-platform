# Edgar Intelligence runbook: initialize

A hosted store initialized from nothing, then its first load of every captured source, and the dependencies between loads. Index: [README](README.md).

## Initialize a hosted store

A hosted PostgreSQL 16 instance (Snowflake Postgres) is initialized with the same commands as the local store, in this
order, by skills and their own commands only. Use
[Connection URLs and environment](../../../skills/data-platform/SKILL.md#connection-urls-and-environment) for the private connection
files, roles and credential handling. The commands below are the whole procedure; each prints names and checksums, never
a connection value.

The stores folder is `~/.config/edgartools/hosted/`, one folder for the store: `connection.env` (the owner logins),
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
2. **Databases.** An instance that holds an old store keeps its logins and gets its databases made again: with the
   operator's word, list them, then drop and create them with the owner and the grants each had:
   ```bash
   set -a; . ~/.config/edgartools/hosted/connection.env; set +a
   python infra/scripts/reset-hosted-databases.py             # lists sizes; refuses while any session is connected
   python infra/scripts/reset-hosted-databases.py --confirm
   ```
   A fresh instance gets its six databases (`mdm`, `rdm`, `rules`, `bookkeeping`, `change_journal`, `silver`) and their
   restricted logins from the stores folder's own files, each login with the password its URL already holds (no login
   is rotated; the first confirmed run also makes the diagnostic login `ops_reader`, with `pg_monitor` and no store, and its
   `reader.env`). Each login gets CONNECT and TEMPORARY on its databases and PUBLIC gets nothing: a load stages its rows in a
   temporary table, and without that right a silver load stops with SQLSTATE 42501 in its step's message. Every URL then
   names the new instance, and the administrator's URLs its new password:
   ```bash
   python <data-platform skill>/scripts/provision_hosted_store.py --service <the instance's saved service>            # lists
   python <data-platform skill>/scripts/provision_hosted_store.py --service <the instance's saved service> --confirm
   ```
   Every load uses one login, `edgar_loader`, which can create nothing: add `--loader` (with `--confirm`) and every
   runtime URL in `worker.env` names it (the old file is kept as `worker.env.before-loader`). It is a member of the six
   runtime roles, so it holds exactly their privileges, and the command refuses it if it could create in any schema of any
   store, owns an object, or is a superuser or can create databases or roles. A store's schema is made and changed by its
   owner login in step 3, never by a load.
   The service is the one the instance's creation saved (snowflake-postgres skill, `pg_connect.py --create`). Wait for
   its hostname to resolve first. Done when the second run prints that every URL names the new instance.
3. **Schemas** (data-platform's step, [STORES.md](../../../skills/data-platform/STORES.md)), each with its owner login, in one shell that holds `connection.env`. MDM and Bookkeeping read the owner
   from their ordinary variable, for that command only; the others read their `*_MIGRATION_DATABASE_URL`:
   ```bash
   env MDM_DATABASE_URL="$MDM_MIGRATION_DATABASE_URL" edgar-warehouse mdm migrate --application-role mdm_runtime
   edgar-warehouse rdm init --runtime-role rdm_runtime
   env BOOKKEEPING_DATABASE_URL="$BOOKKEEPING_MIGRATION_DATABASE_URL" edgar-warehouse bookkeeping init --runtime-role bookkeeping_control
   edgar-warehouse change-journal init --runtime-role change_journal_runtime
   edgar-warehouse silver init --runtime-role silver_runtime
   edgar-warehouse rules init --agent-role rules_agent
   ```
   `init` is the whole step on a fresh store; `migrate` follows an `init` only when a later schema file arrives. Done when
   each prints its schema file's checksum.
4. **RDM codes.** With `worker.env` sourced, `python <data-operations skill>/scripts/rdm_restore_published.py --by <name>
   --words "<their exact words>"` (the operator's words go in the approval record). Done when every pin reads `pin ok`.
5. **Registration login.** With the owner connection, `env MDM_DATABASE_URL="$MDM_MIGRATION_DATABASE_URL" edgar-warehouse
   mdm grant-registration --role mdm_governance`. It lets the restricted login read the stored records and write the
   policy and dataset tables, and nothing else.
6. **Source configurations.** `edgar-warehouse rules check` (every source, offline), then, with `governance.env`
   sourced, `edgar-warehouse rules register`. Done when it prints a digest for the merge rules and every Dataset Contract.
   Then the silver tables (data-platform's step; a load creates none and stops when one is missing):
   `bash infra/scripts/deploy-silver.sh ~/.config/edgartools/hosted/connection.env`.
7. **Worker grants**, with `connection.env` sourced, one per worker profile:
   ```bash
   for p in $(python -c "from edgar_warehouse.workers import PROFILES; print(*PROFILES)"); do
     env BOOKKEEPING_DATABASE_URL="$BOOKKEEPING_MIGRATION_DATABASE_URL" edgar-warehouse bookkeeping grant-profile --profile "$p" --worker bookkeeping_runtime
   done
   ```
   Done when `doctor` prints `"ok": true` under `worker.env` (it checks MDM, Rules, Bookkeeping and the Change Journal; steps
   4 and 6 prove RDM and Silver) and `load --plan` reads a capture.

A missing grant or login that a command names is a gap to fix through the central connection section, not to work around.

## Load a fresh store

`rules/load-chain.yaml` holds the order of every source and target, each one's capture, workers and the facts and revision no capture states, and
`scripts/load_chain.py` runs it, so a store is loaded the same way every time and nobody rewrites the list:

```bash
python <data-operations skill>/scripts/load_chain.py --plan     # documents and bundles per step; writes nothing
python <data-operations skill>/scripts/load_chain.py --auto      # watch the loads; start each step when its lane is free
python <data-operations skill>/scripts/load_chain.py            # one process, the steps in file order; stays awake
python <data-operations skill>/scripts/load_chain.py --from <step>   # carry on; a step that is done costs one call
```

**`--auto` is the way to load a store.** It starts the step at the head of every lane whose dependencies are done, longest
first, while a slot is free (`--slots`, by default half the machine's gigabytes, at most its cores, at least two) and the machine has
headroom (a load average under one and a half times the cores, swap under three quarters used); it also reads the database as the reader login (a step starts only while fewer than three sessions wait on locks, none for a minute, and
less than four fifths of its connections are in use), and it starts one step a
cycle, since the load average lags. It moves each running step's workers within its capacity profile's range (`--capacity`) by the readings: the step with the
longest chain behind it doubles when there is room, and the step with the shortest halves when the machine or the
database is pressed, by stopping its load and starting it again (a load resumes where it stopped). Priorities and the projected end use each step's measured minutes (its first start to its `done` line) where it has run, and
an estimate where it has not: its bound times the share of its bound the done steps used. A running step that outruns its
estimate has disproved it, and the projection then counts its bound, so it is an upper bound, never a promise. The
scheduler aims for `--connections N` database connections (250 by default): workers rise while fewer are in use and the
machine has room, and it says when the machine, not the database, is the limit; to use more connections, run the loaders
on more compute (production runs them on AWS). With `--hours H` or
`--deadline HH:MM ET` the run is held to a strict deadline: a run behind its schedule is allowed twice the cores in load, and
at the deadline every step it started is stopped and it names what is left. A step that uses up its attempts blocks its lane and whatever waits for it; the
rest carry on, and the scheduler stops, naming what cannot start, when nothing else can. Every step runs as
`load_chain.py --only <step>`, so the attempts and the one-load-of-a-source-and-target rule are the same as by hand.

**A fresh store starts a fresh state file.** The chain's `done` lines are read from `chain-<RUN>.log`, which names the store it belongs to (by its instance's address,
never shown). A run against another store sets the old file aside as `chain-<RUN>.log.<store>` and starts a fresh one, so an
earlier store's lines never satisfy a wait.

Masters come first and each source's silver target last, so silver rows find their masters as they land; a silver step
needs none before it (a row lands with its link key, and `--finish` fills the master ids). A source's later
delivery is a new publication and carries the next `--revision`. The chain stops at the first step that does not finish
in its attempts and names why in that step's log. After the last step it builds the lookups and the links table, once
each, and fills each silver table's master ids (`--finish` runs only those). Check a running chain every 30 minutes; a step that stops reports at its
check, never on a tighter loop.

### The links table is built once

The links table is built whole from every stored record (`edgar-warehouse silver links`), so no target carries a step
for it. A `load` run alone builds it after its last bundle when it mastered anything; a load that is one of several
passes `--no-links` and the last step builds it (the chain's `--finish`). A newly mastered record can be the end a
stored link waited for, so any load that masters builds, whatever its source states.

### Dependencies between loads

Loads depend on each other only as the rules say, and `python <data-operations skill>/scripts/infer_dependencies.py` prints it from
the rules files: nothing here comes from a machine's size. No source needs another loaded first: the Merge Stage holds a
record that finds no master and releases it when a later file gives one, so a load that runs early is never wrong. The
rules state three kinds of ordering:

- **Must** (a load leaves something out otherwise). A target that publishes a second batch of its source's records follows the
  target that publishes the first. The lookups, the links table and each silver table's master ids follow every load (`--finish`).
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
   use beyond the machine's, shown by swap and a load average above the cores, slows every lane: add lanes when the
   running ones leave memory free, and start the longest first.

**`--plan` proves the documents, not the rest.** It counts what each step would read; it does not open a file a step reads
beside its capture, and it does not write, so it cannot find a missing right. A fresh store's first minutes find them:
a lane stops when its step uses up its attempts (the chain file sets them for each step) and names the step. Read its reason where the step's log points, the stores folder's
`load-errors.log` (one file for every lane: find the step's own command and its last lines), fix the cause, and run the
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
