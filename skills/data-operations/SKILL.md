---
name: data-operations
description: Operates every domain and applies the DDL for MDM, RDM, Bookkeeping, Change Journal and silver on PostgreSQL, MySQL or SQL Server Express. Use when making those stores operational, applying a schema or an approved silver spec, operating daily loads, loading with grain: run / no bookkeeping, checking source readiness, reporting load timings, managing a backlog, monitoring a run or maintaining its operational runbook.
---

# Data Operations

Work lean: check each step against [the seven wastes](../data-platform/SKILL.md#the-seven-wastes) and drop what adds no value.

Operate existing sources repeatedly using their configured engines. Maintain the
source's operational runbook and report verified progress with counts and reasons.
Acquisition supplies completed deliveries independently. A catalog `Pipeline` entry describes a
load and never starts or resumes one ([execution boundary](../openmetadata/SKILL.md#pipeline-execution-boundary)).

## Find the root cause, silently

A step that fails, a reading that disagrees with another, a retry about to be the fix, or a surprising time: find the root
cause by the [five whys](../data-platform/ROOT-CAUSE.md) before acting or reporting, silently, and report the conclusion.

## Publish a step's status to the catalog

The catalog describes the load; it takes no part in one (the
[openmetadata skill's pipeline execution boundary](../openmetadata/SKILL.md#pipeline-execution-boundary)). A load neither reads
nor writes it: readiness has no catalog check and a finished step publishes nothing. The catalog's server need not run. After
a load, `load_jobs.py --catalog-status` publishes each done step's latest Bookkeeping run as the target Pipeline's status
(`rules catalog status --bookkeeping-run`), when the catalog's address and token are in its private file (`OPENMETADATA_ENV_FILE`,
else `~/.config/edgartools/openmetadata.env`, else the checkout's `.env`). A status that cannot be published is a note in the run's
state file. Initializing the catalog's credentials is the openmetadata skill's.

After a reset the catalog still says "Successful" for each step from before: history, which each step's new run supersedes. Read a status
with its run's time, never delete the old ones without the operator's word, and bring the catalog's text up to the rules once the stores
are initialized, on its own (the init runbook's catalog step, `docs/runbooks/edgar-intelligence/init.md`, owns the commands).

## Report a running load from its evidence

Never report a load as "running". Run `load_jobs.py --status --run <label>` with the exact `RUN` passed to `infra/load-pipeline/load.sh`; the output names it.
Omitting `--run` may inspect a different run's state. `--json` feeds [load-monitoring](../load-monitoring/SKILL.md). For each step, report:
how long against its bound, how far (bundles done and the minutes left at the rate so far), what it wrote (rows a minute
in its store, and which other running steps share that store), its processes' CPU and memory, the age of its log, and its
verdict. The database sessions are shown by store (working, or waiting on the client), read as the reader login.

Read the verdict, not the word "running":
- **progressing**: its processes worked, its log moved in the last ten minutes, or one of its own database sessions (tagged `chain-<step>`) is active or
  changed state lately; a neighbour's writes never count. There is no "unclear": a step that is not progressing is stalled, with five whys;
- a step that **stopped**: read its own errors file (`chain-<RUN>-<step>.log.attempt-<n>.errors`), not the shared error log;
  an unchanged failure, or a refusal the same inputs always give (contradictory publications), stops the step at once, naming its cause, and that run is `abandoned`;
- **no sign of work** (stalled, with its five whys printed): no CPU, no session of its own working and a silent log: read its log and the stores folder's `load-errors.log` (and `.1`, rotated at 10 MiB)
  before saying anything else, since it may be stalled;
- **waiting on database locks** (three or more sessions): the contention ladder of the daily-run runbook;
- a store note, **client-bound, not the database** (more than half its sessions waiting on the client): the machine
  running the loads is the limit, so more workers on it will not help; run the loaders on more compute;
- **cannot finish in its remaining attempts**: raise its workers or its minutes now, not at its last attempt.

A step's workers are found by their parentage (a spawned worker's command line names no source) and the count shown is the one
the load was started with; a step that reads 0% CPU with several workers is a status that missed them, not an idle step.
A single-document step has no progress in its log: say so, and report its database rows and sessions. A store's rows are
shared by every step that writes it and cannot be split: say which steps share it. Check a running load every 30 minutes
and report what changed, with the evidence, not that it is still going.

## One login for every load

A load connects as one login, `edgar_loader` (`worker.env`), for every store. It is a member of each store's runtime
role and can create nothing: a load changes rows, never a schema, so a load that needs a table stops and names the
command (below). Once nothing holds the six runtime logins, retire them with `provision_hosted_store.py --loader --retire`. Diagnosis uses the reader login, not this one.

## Diagnose with the reader login

Diagnosis (sessions, locks, waits, connections, what a load is doing) reads the database as the diagnostic login in
the stores folder's `reader.env` (its `DATA_URL`, `CONTROL_URL` and `CONFIG_URL`): it has `pg_monitor`, which shows sessions, locks and
statistics and the catalogs of each store (who holds what), never a table. Never diagnose as the owner, the administrator or a
runtime login: each can change or read data, and a diagnosis that needs more than the reader shows is a gap to name.
`load_jobs.py --auto` reads the database this way; [database-monitoring](../database-monitoring/SKILL.md) has the readings.

The scheduler judges the machine by what is happening now: the load average against the cores, and memory free. Swap used presses
only while memory is short, because the system keeps swap long after the load that filled it; reading swap alone holds every
start back on a machine with memory to spare.

## Start with live state

Resolve the requested environment, source and retained delivery from existing
configuration and evidence. Reuse the current authorization for that scope.
Read the source's runbook and live Bookkeeping runs/leases before starting work;
another agent's in-flight work is a dependency, not a cleanup target.

Use the Edgar Intelligence runbook (`docs/runbooks/edgar-intelligence/` in the repository: initialize, daily run and CI/CD, kept outside this skill so their steps and dependencies change without it) for last-run lookup, delivery, file-change, capacity and recovery.
Discover actual command capabilities with `edgar-warehouse doctor` and
CLI help. Report missing enforcement or unsupported stages as runtime gaps;
instructions cannot make them available. An offline sequence check is not a
runtime readiness certificate. To install, enable and run one source, then
clear a finished test, follow **Install and enable one source**. To load a
captured delivery, use **Load a capture**: one command for every source. Recover
retained progress before making a new run.

When deploying tested configuration to an environment, follow **Configuration
promotion** in the Edgar Intelligence CI/CD runbook. Reuse the existing Rules approval procedure and exact
release evidence; distinguish an approved release from its active deployment.
For how long each load took, use [retained load timings](TIMING-REPORTS.md): resolve the configured log directory and run label, report every step and total wall time, and distinguish the timing evidence from catalog summaries and live monitoring.

## Tables are created elsewhere

This skill creates no table, and neither does a load. A store's schemas and every committed silver table are data-platform's ([STORES.md](../data-platform/STORES.md)); a new source's silver tables are data-onboarding's ([TARGETS.md](../data-onboarding/TARGETS.md)). When a load stops on a missing table, hand it to one of the two. Pass one command's owner URL as `KEY=value command args` (a binary may use `env KEY=value command`; a shell function takes the assignment only).

## Operationalize every domain

Do this after the five schemas are current, for every domain. A domain is one
source directory under `sources` together with every entity kind that
source's merge policy names. Walk all of them. Two named kinds are not
the whole list.

1. **Stores.** Confirm the five schemas in **Apply store DDL** and Rules are
   current on the selected engine. Route a dialect refusal as missing engine
   support; retain that target's blocker while independent targets proceed.
2. **MDM, per domain.** Follow **Configuration promotion** in the Edgar Intelligence CI/CD runbook for
   that source and its merge policy. Read back the active version. A domain
   whose source or policy is still a draft, or whose activation is refused,
   stays blocked. Record the refusal and go on to the next domain. Loading
   entities waits until that version is the active proven one.
3. **RDM, per domain.** A new store's RDM is empty: restore every published code set from git with
   `scripts/rdm_restore_published.py` in this skill
   (with the runtime connection from [Connection URLs and environment](../data-platform/SKILL.md#connection-urls-and-environment);
   it drafts, approves under the operator's standing ruling (no approval is asked), publishes and checks each version's sha256
   against its `pin.json`, and exits 1 naming any that differs). Then `edgar-warehouse rdm list`, then
   `edgar-warehouse rdm describe <code set>` for every code set that domain
   pins. A published version is operational. A missing or draft code set is a
   blocker for that domain: route it through data-profiling's RDM steps
   (`rdm draft`, `rdm diff`, operator `rdm approve`, `rdm publish`). Leave the
   code set unpublished until those words exist. A code set keeps one version: publishing deletes the
   one it replaces, `rdm retire` removes it, and `edgar-warehouse rdm prune [<code set>]` cleans a store an earlier build left with more.
4. **Check the silver tables.** Data-onboarding registers each part's approved spec
   ([TARGETS.md](../data-onboarding/TARGETS.md)); this skill creates none. For each part,
   `edgar-warehouse silver created <spec>` then `edgar-warehouse silver describe <table>` with the runtime login.
   Report a table only after its registry entry, comments and restricted grants read back. A part with no
   approved spec, a table not created, or a pipeline silver step
   with no worker, stays blocked and is reported. A source whose target has a
   `silver.land` step lands through it; `silver land` stays the manual write
   for a table whose source has none
   ([data-onboarding](../data-onboarding/SKILL.md), Two targets).

A domain is operational when its MDM source and merge policy are the active
proven versions, every code set it pins is published in RDM, and every approved
silver spec is a registered table. Report one line per domain: operational, or
the blocker. The recurring loop below then loads that domain's entities from a
finished delivery. This section does not download, does not invent a command,
and does not mark a blocked domain complete.

### Reload RDM from the published code sets

`rules/reference/published/<set>/<version>/` keeps a version's codes and sha256, not the code set's
own words or where its codes came from. An empty RDM database is reloaded from those files with
`PYTHONPATH=. uv run python scripts/dev/reload_rdm.py` (the RDM login from the environment). It
drafts each version, approves it under the operator's reload words, publishes it into a temporary
folder and refuses unless the bytes equal the file and its pin; a version already held is left
alone. Each set's words and source are in `WORDS` in that script, and in RDM itself (`edgar-warehouse
rdm describe <code set>`: its authority and the evidence of its first version). Publishing a code set
adds its entry in `WORDS` in the same change; a skill whose domain uses the set names its source (the
skills of the domain carry a section "RDM code sets and their sources").

A stopped local store starts again only from the checkout that owns it
(`identity.json`, `owner`), and only when that checkout's baseline migration is
the one the store was built with: `up` stops at "Installed migration checksum
differs" otherwise, with the container running but its env files still naming
the old port. Such a store is not upgraded in place; master into a fresh store
instead of rebuilding one other tickets' data lives in.

## Qualify Silver storage

Read [STORES.md](../data-platform/STORES.md), "Qualify Silver storage", before declaring a Silver store ready on an engine.

## Install and enable one source

Read [INSTALL-SOURCE.md](INSTALL-SOURCE.md) when the task is to load and master one Rules source before the next. On the hosted instance read [HOSTED-LOADS.md](HOSTED-LOADS.md) first.

## Load a capture

One command loads a captured delivery through one source's target, from start to finish. It knows no source, target or store by name. Everything comes from the rules files and the stores folder you give it.

```bash
edgar-warehouse load \
  --source <source> --target <target> \
  --capture <capture folder> --capture-run <capture run id> \
  --stores <stores folder> \
  --workers <readers> --bundles <runs at once> --minutes <window>
```

**A load uses `grain: run`**: one run row, no units or leases ([bookkeeping grain](../bookkeeping/SKILL.md#grain-how-much-bookkeeping-a-target-uses)). Write `grain: run` on every target (a test refuses one that does not); a run started without it is [By the unit](UNIT-GRAIN.md). Start a load only through the pipeline, never from a checkout: `infra/load-pipeline/load.sh <step>...` runs the load jobs in the image CI built from `main` ([HOSTED-LOADS.md](HOSTED-LOADS.md#where-a-load-runs)). Load every captured source through the load jobs (Edgar Intelligence initialize runbook) with `load_jobs.py --auto`: it watches the loads and starts each step when its lane is free, in the load jobs file's `priority` order (the init runbook's "Load priority" table), then the longest chain (`--lane` A P S C L O D F G N Q and then `--finish` is the same by hand); `waits_for` is the dependency order, and a fresh store starts a fresh run state file: a run label can repeat, and a state file written for another store or another generation of this one, or with no marker, is set aside, kept and never a reason to stop (a file from before generations is trusted and learns its generation at its next start; `--status` says when the next run would set the file aside). Size `--workers` and `--bundles` by **Fit the load into the window**.

- `--stores` is the stores folder configured through
  [Connection URLs and environment](../data-platform/SKILL.md#connection-urls-and-environment).
- **A proof runs today's engine.** Rebase its branch onto `origin/main`, then `uv sync --reinstall-package
  source-contract` (a plain sync keeps the built engine); a branch cut just before an engine merge measures the old one.
- **Create a store from an up-to-date checkout, and keep its lifecycle there.** `up` refuses a checkout
  behind `origin/main`, and a store belongs to the checkout that created it: `up`, `stop`, `backup` and `copy`
  from another checkout stop at "Environment belongs to another worktree". A stale untracked skill link
  blocks fast-forwarding the main checkout; remove the link (not its target) first.
- Add `--fact name=value` and `--file name=path` for each input the target's
  `run` declares; `scripts/run_inputs.py <source>` in the data-onboarding skill lists them.
- **A delivery's date is read from the capture, never typed.** A target whose files carry the date in their names says
  `delivered: {key: <pattern naming year and quarter, month, or month and day>, fact: <run fact>}`: the load fills the
  fact and takes the publication's revision from the date, and prints both. Giving that fact by hand stops the load. Write
  `delivered` on a new target whenever the file name states the date; type a fact only for what no captured file states.
- **A load creates no table.** Only data-platform (store setup, [STORES.md](../data-platform/STORES.md)) and
  data-onboarding (a new source's tables) create tables. A load checks
  each table it writes with its runtime login (`silver created <spec>`) and stops before it submits anything when
  one is missing or holds another spec. A load never reads the owners' logins.
- **Look on the machine before asking to capture.** Reading retained files needs no provider request, so search
  every place below before asking for one. Say which you found: a cohort proves a path, never a delivery's totals.
- **The engine reads no gzip.** A folder of `.gz` files stops as "malformed": unzip a copy, then write its receipts.
- **A capture left by `provider.capture` has no `receipts.jsonl`.** Run
  `scripts/capture_receipts.py <capture folder>` once: it writes one receipt per
  file and never replaces a receipts file.
- **A reload whose inputs changed needs `--revision N`** (default: the revision the delivery's date gives, which the
  load prints, else 0). A changed input (a new Name Matching, say) changes a record under the
  same revision, and the Stage refuses it ("Source native revision has
  contradictory publications"): pass a revision higher than the last load's.
- **Plan when in doubt.** Add `--plan` (no `--capture-run` needed) before claiming or
  starting a load you doubt (a changed rule or capture); a routine load needs none. It changes nothing and prints which open runs `load` would
  finish, which it would leave and why (a run pinned to old worker code is
  left, and its documents load again in a new run), a blocked run that would
  stop it, and the documents and bundles.

What it does, in order:

1. **Finishes what is open.** A run of this source and target that is still
   running or waiting is driven to the end first.
2. **Picks the documents.** It takes the capture's receipts that match the
   target's first step's `files` pattern, or every receipt when no pattern
   is given.
3. **Cuts bundles.** Each bundle holds at most the source's
   `execution.max_artifacts` documents.
4. **Loads each bundle.** It prepares the bundle (`mdm prepare-capture`),
   submits it (`rules run`), works each step in its declared order and
   finalizes. `--bundles N` loads N bundles at once. Each is its own run,
   because bundles of one target are one wave, not a
   queue, and on PostgreSQL their silver rows merge by key side by side (a snapshot takes the whole table). A bundle that stops does not stop the others. Once `--minutes`
   has passed no new bundle starts, and every stop is named at the end. The Change Journal leaves out documents already loaded under
   these rules. Already-loaded documents are counted and skipped, and an
   unchanged rerun starts no work. "These rules" are the source's own rules and the part of the merge policy that
   acts on it (its rules, their identifier contracts, the kind's field defaults), so a rule of another source does
   not load its documents again. If a bundle says `512 of 512 documents to load` when you expected `already loaded`,
   something in that slice changed: find what before the load spends hours.
   **Force publish** (`load --force`) is the explicit exception: it ignores the Change Journal and processes every
   document of the source again, as a new publication of the capture run (`<run>+force-<time>`); the journal records
   it as forced. Use it when the result must be made again whatever the journal holds (after `mdm clear-source`,
   or to rebuild from retained files). Never for a daily run. Through the pipeline: `RUN=<new label> infra/load-pipeline/load.sh --force`
   (every load job, or the named ones); a new `RUN` keeps the forced load's state apart from the earlier one.

It prints one line per bundle as it goes. At the end it prints a JSON
summary: documents loaded, documents already loaded, and each run's id and
counts.

**Stopping is safe.** A session deadline, a closed laptop or a failed unit leaves
the run resumable. Run the same command again. It finishes the open run
first and never loads a document twice.

### A load needs no file made for it

A source's records all go to the Merge Stage, and the matching rules decide there what each joins. A load is
never given a list of which records to take: a record that finds no golden record waits in the Stage, or is
created, as its entity type's rule says. A target's `run` names only facts the caller must bring (a capture run,
a time, a count the provider states).

Declared `preparation` operations finish before new bundles, under the selected worker login. Reuse a hash-bound
cached projection only for identical bytes, population, recipe, policy and runtime; an unchanged repeat applies
nothing. EOF and count verify the declared complete scope; independent provider completeness needs publisher
evidence.

### An entity type is complete when all its sources are mastered

A golden record of an entity type comes from every source whose records name one, not from a single source. So
one source's load is that source's part of the entity, never the entity.

- **Report a load as a contribution.** Say which source loaded, how many of its records were mastered and how many
  its classification set aside (counted apart, never as mastered), and which sources of that entity type are still
  missing. "The entity is loaded" is true only when every source of the kind has loaded.
- **The entity is done when** each source of its kind has loaded, the links between them have run (identifier
  joins as records arrive; name pairing through its pass where the rules declare one), and the explained count
  finds no record unexplained, counted for every source at once.
- **Do not size the entity by its first source.** The count after one source is what that source's classification
  passes, not the entity.

### Examples: an entity from several sources

The Company entity is mastered from the SEC company filers, the N-PORT registrants, Form ADV advisers and
custodians and GLEIF. After the SEC company source alone, the count is the listed operating filers it passes (the
rest are set aside by its classification), not the Companies; GLEIF joins the Company that holds its LEI or creates one for an active general entity, and
the SEC Companies pair with GLEIF through the waterfall pass, which runs first so a paired record joins its filer. A Security is mastered from OpenFIGI, N-PORT
securities and 13F securities in the same way.

### Where retained files are

Under `~/.local/share/edgartools/mdm/`, `captures/` holds whole deliveries and `proving/` holds cohorts. A source names
its own: `sources/<source>/inputs.yaml` lists each delivery by name with its folder (and `root: proving` for a cohort),
and a step of `rules/load-jobs.yaml` loads them all in order, or names one kind with `input:`. A step's name holds no date: a new file is a line there. Read that file, never a list copied here;
`load_jobs.py --list` shows each step's resolved folder. A new delivery is a new entry there.

`~/edgar-local-tmp/` holds working copies from earlier tests.

### When it stops

Run the same command again after fixing the cause: it finishes the open run first.

| You see | It means | Do this |
| --- | --- | --- |
| `N of M did not finish: <bundle>: <error>` | A bundle stopped, or `--minutes` passed before it started. The others went on. | Read the named error (the database's own line, `(psycopg2.errors.X)`, not the driver's last line), fix it, run again. |
| `Run <id> ended <state>, not complete; its checks: ...` | A run check did not pass. | Read `bookkeeping status <id>` (`run.checks`). Never submit the bundle again. |
| `Run <id> of <source> <target> is blocked` | Bookkeeping stopped that run under the active rules version, on corrupt or missing evidence. | Recover it ([recovery](../bookkeeping/RECOVERY.md)), then run again. |
| `declares no <target> target` | No target of that name in the source file. | Use a target listed there. |
| `lands silver table(s) ... with no silver-*.yaml spec` | The target lands a table no spec describes. | Add the approved spec ([data-onboarding](../data-onboarding/TARGETS.md)). |
| `all N documents already loaded` | The Change Journal holds every document of that bundle under these rules. | Nothing to do. |

Two kinds of run are reported and left as they are, and their documents load again in a new run (the Change
Journal never recorded them): a blocked run under a retired rules version, and an open run pinned to other
worker code. A unit that failed, a lease or a pinned worker is [By the unit](UNIT-GRAIN.md).

### Restart a running load for new code

A restart starts a new run when the worker code changed, so it reads and prepares again and its merge
passes over every batch it already merged. Price both before stopping a load (measure the read and prepare
time and the seconds a merged batch costs); restart only when the gain beats that cost, and let a nearly
finished run finish.

### Restart one source from empty

A source loaded under rules that no longer fit it (a Dataset Contract that got a new dataset code, a rule that
changed what its records join) is cleared and loaded again. Never delete rows by hand.

1. **Count first.** With the store's owner connection from [Connection URLs and environment](../data-platform/SKILL.md#connection-urls-and-environment)
   (the runtime role may not delete decisions):
   `edgar-warehouse mdm clear-source --source <dataset code>`. It runs every delete and rolls back, and prints what
   would go: the source's records, the golden records only it made (with the aliases of their merges) and what hangs
   on them. It refuses, and clears nothing, when a golden record also holds another source's records: replay those
   instead.
2. **Say it to the operator, then `--confirm`.** It is one transaction; a second run removes nothing.
3. **Load again.** Reload the rules under a new version label and activate them (merge policy first), then
   `load` with a **new** `--capture-run`. Runs left open before are finished or left as they are (see "When it
   stops"); their documents load again. Silver, Bookkeeping and the Change Journal need no clearing: a changed
   dataset code or rules version is a new processing identity.
4. **Read the load's own report** (`Done: N documents loaded`, and the runs it finished or left) before the next source.

### Fit the load into the window

The operator names the window. A plan that does not fit it is not the plan.
Work it out from counts before starting:

1. **Documents and bundles.** Count the documents not yet loaded, and divide
   by `execution.max_artifacts`.
2. **Wide and narrow steps.** A wide step has one unit per file or group
   (`source.read`). A narrow step is one unit per bundle (`mastering.merge`,
   `mdm.prepare`). Only more bundles at once shorten narrow steps in total.
3. **Bundles and readers.** The workers a step can carry come from the compute it runs on, its capacity profile (`load_jobs.py --capacity <local | aws-small | aws-medium | aws-large>`, the profiles in `rules/load-jobs.yaml`): a worker is sized at half a gigabyte and four share a vCPU, so a 1 vCPU, 4 GB task carries up to 4 and a 2 vCPU, 8 GB task up to 8, and a bigger task a new profile with no code change. A step starts at the load jobs file's workers held to the profile's range, and `--auto` moves a long step (the two-minute sample will miss the window, or a step already ran past ten minutes) within that range, raising it at most once in ten minutes (each move abandons the bundles in flight) and shedding at once when the machine is pressed; `local` is this machine measured at half its memory. `--workers` is the processes on each step at either grain, shared out to a step with fewer units (Resource sizing (Edgar Intelligence runbook)); keep `--bundles` × `--workers` near the core count. `load` never starts more workers than a step has units left. A merge into shared masters stays at one bundle when memory is the limiter.
4. **The bound.** Measure one bundle first (`load` prints each run's
   minutes). The load takes roughly (the number of bundles ÷ `--bundles`,
   rounded up) × that time.
   Expect each bundle to run slower when the cores are shared. A target that
   reads another target's runs waits for that target. If the total does not
   fit the window, say so and do not start. Never drop files to make it fit.
   Time the first bundle of every source this way.
   Keep the machine for the load: a load sharing its Docker with a large test run stops bundles (a deadlock, a closed
   connection, a failed read) and finishes late; a stopped
   bundle is resumed by running the same command again.
5. **Memory and shared masters, not only cores.** Bundles of one target
   that merge into the same masters collide: with several bundles at once
   on a small machine, most merges stop "Prepared state changed; re-assess"
   and others are killed for memory (status -9). Even one at a time, a merge
   can be killed for memory. Run such merges one bundle at
   a time, and measure one merge's peak memory against the free memory
   before choosing `--bundles`.

   **Lesson:** a merge that saved every batch can still die writing the receipt if that step reads every payload at once; count applied batches before blaming the saves, and measure a merge that has never run (a rerun that only writes the receipt measures nothing about saving).

### While a load runs

- **A long run shows its progress.** Sample any run over ten minutes in its first two minutes with
  `scripts/dev/run_sample.py`. Send its output to a file, unpiped: a `| tail` hides a slow page until the run ends. A
  build with no progress line gets one before it starts.
- **Keep the machine awake and on power.** Sleep stops the workers; the same
  command resumes the load, with nothing loaded twice.
  On macOS, check `pmset -g` (`sleep`): while the machine sleeps, Docker,
  every test container and the shared server freeze, and brief Power Nap
  wakes make a run look slow, not stopped. Start a long run or test as `caffeinate -i <command>`.
- **Measure a slow load with `scripts/profile_load.py`, never by hand**.
  `progress` shows, for the running runs, the units in each state per step and how long they have run: the
  answer to "how far is it", and it lists runs left `running` by a load that was stopped.
  `failures` groups the units that hold an error by step, state and error shape, with counts: read it before
  opening the load log.
  `steps` gives each step's share of a finished run;
  `sample` ranks what the database ran, once a second. Configure profiling connections through
  [Connection URLs and environment](../data-platform/SKILL.md#connection-urls-and-environment).
  For a statement inside a function, set `shared_preload_libraries=auto_explain` with
  `auto_explain.log_nested_statements=on` and read the server log. The first answer is the step; the second,
  the statement.

### One design for every target

A target that differs from the others with no reason in its data is a defect. Before a new or changed target
merges, expand every source's targets into one table, setting by setting (grain, run facts, files read, steps,
lease settings, workers), and explain each difference by the data. A setting no code reads at that target's
grain is deleted. A captured file is read once however many targets read it: a load takes the extract another
target of the stores wrote from the same content with the same rules and worker code (kept by content under the
manifest root's `extracts` folder), so give two targets that need the same extract the same rules file and context.
A second target stays only where it is a second publication or lands another table. Do not write a source-specific driver script: a missing step is a gap in
`load`, fixed there. `--workers` is the one setting an operator sizes: processes on each step. A source's
`execution.workers` is threads inside one read unit, worth setting to 2 only where a unit reads many files.

## Operate the recurring loop

1. **Inventory and readiness.** Account for the entire declared delivery and its
   acquisition completion evidence, expected/available file counts and receipt
   hashes. Check approved processing versions and required references. An existing
   folder or timestamp alone cannot establish downloaded-and-ready status. Let
   independent ready sources proceed when another source is delayed; hold only
   genuinely dependent work. Never start acquisition to resolve a missing delivery.
2. **Changes.** Compare with the last verified inventory and consult the Change
   Journal under the actual processing identity. Distinguish new bytes, changed
   rules/shared inputs, suspected renames and schema drift using the Edgar Intelligence daily-run runbook. Route
   new feeds to [data-onboarding](../data-onboarding/SKILL.md), shape/meaning changes
   to [data-profiling](../data-profiling/SKILL.md), and existing rule changes to
   [refining-rules](../refining-rules/SKILL.md). Routine deliveries reuse applicable
   qualification and approval; missing version evidence is reconciled, not invented.
3. **Size the work.** Measure usable CPU, memory, disk, database connection budget
   and competing work at the actual execution host/container. Fit the load into
   the window (**Load a capture**) before choosing `--bundles`. Use prior verified measurements and current supported bounds to choose
   concurrency and bundle size.
   Unknown estimates start conservatively; exhausted
   resources wait. Size divides the whole backlog into work, never drops records.
   A proof is not this step: [Choose the cheapest proof](../mdm-engineering/SKILL.md#choose-the-cheapest-proof)
   stops once every new case is shown. A load still takes every file.
4. **Submit or resume.** Run `edgar-warehouse load` (**Load a capture**): it
   resumes an open run before submitting. Underneath, use [Bookkeeping run](../bookkeeping/RUN.md) and
   [recovery](../bookkeeping/RECOVERY.md) for the existing task protocol. Keep the
   source-owned steps, original input/rule/reference/runtime pins and authoritative
   leases. Run declared local prerequisites only through supported approved paths.
   A preferred `after` order does not pull another source into this run. When
   the task is one source at a time, follow **Install and enable one source**
   and finish that run before the next source. Missing common-command support
   remains a blocker, not permission to invent source-specific orchestration.
5. **Work.** Each worker checks its own units. Adjust dispatch
   between invocations within supported limits as capacity changes. Changing a
   frozen contract or input requires new work; preserve the existing run. Inspect
   progress, contention, failures and pending events with bounded queries. Use
   [Change Journal](../change-journal/SKILL.md) for receipts/delivery recovery through
   the producer that owns the outbox, never direct edits to journal or run state.
6. **Close or hand off.** Finalize only after every declared unit is complete,
   source outcomes reconcile and required Journal deliveries are acknowledged. An
   unchanged repeat should select zero files and start no mastering work. Report a
   partial run honestly. Save the run ID, frozen evidence references, resource
   measurements, blocker and next action in the source runbook for the next agent.

For a monitoring request, check every 30 minutes and exit on completion,
blockage, cancellation or the deadline. A quiet interval sends no message.
At expiry retain resumable state and report the next action.

### Schedule a recurring load

A schedule repeats steps 1 to 6 above; it adds no step of its own.

- **What may be scheduled.** A `load` of files that are already captured. A
  scheduled run never starts acquisition and never makes a provider request. A
  schedule that would fetch is a different job: it needs the operator's
  permission for that request, recorded in the schedule itself with the words
  and the time.
- **Where it runs.** On the machine that holds the store, because the load
  needs the store's connection files. The agent runtime's scheduler can run a
  session-bound interval there; a hosted routine reaches only a hosted store.
  A hosted production load writes Silver to Snowflake `EDGARTOOLS_SILVER` and
  MDM to Snowflake-hosted Postgres. `--stores` selects connections, not an
  environment by itself: verify they target the requested hosted stores before
  planning or loading. See [AWS and Snowflake
  operations](../aws-snowflake-operations/SKILL.md#data-layers).
- **What one scheduled run does.** Read `profile_load.py progress` first. An open
  run is resumed by `edgar-warehouse load` and is never submitted again beside
  it; runs left `running` by a stopped load are reported, not reused. Then load,
  and report with `progress`, `failures` and `quality`: counts and times, no
  values.
- **How it ends.** Every schedule carries a deadline and an exit for each
  outcome: complete, blocked, cancelled, deadline. A quiet interval sends no
  message; a failure or a finished bundle does. At the deadline it keeps the run
  resumable and reports the next action.
- **Who owns it.** The schedule names the source, the capture folder, the store,
  the interval and the deadline in its own prompt, so the next agent can read,
  change or stop it without asking.

## Durable owners

| Owner | Authority |
| --- | --- |
| Rules | Versioned, tested and approved processing configuration |
| Bookkeeping | Runs, worklists, dependencies, leases, checkpoints and verified progress |
| Change Journal | Durable events and verified processing/delivery receipts |
| Destination | Atomic writes, identity, constraints and commit evidence |
| Operational runbook | References, measurements, observations and next actions; never authority to mark work complete |

Use the existing shared stores and private role connections. Preserve captured
data, source identities and exact integer precision. Public reports contain counts
and invented examples; keep credentials and row-level evidence private.

## Handshake

Owns the run and its recovery. Gives [load-monitoring](../load-monitoring/SKILL.md) the load jobs' status, the run label and the lane budget, and acts on what it reports (restart the runtime, recover with [bookkeeping](../bookkeeping/SKILL.md)). Sends a failure nothing explains to [production-support](../production-support/SKILL.md) with the run label and logs. Reads [access-audit](../access-audit/SKILL.md) in readiness. The catalog takes no part in a load. The table of who owns what and hands off to whom is [OWNERSHIP.md](../data-platform/OWNERSHIP.md).
