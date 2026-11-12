---
name: data-operations
description: Operates every domain and applies the DDL for MDM, RDM, Bookkeeping, Change Journal and silver on PostgreSQL, MySQL or SQL Server Express. Use when making those stores operational, applying a schema or an approved silver spec, operating daily loads, checking source readiness, reporting load timings, managing a backlog, monitoring a run or maintaining its operational runbook.
---

# Data Operations

Work lean: check each step against [the seven wastes](../data-platform/SKILL.md#the-seven-wastes) and drop what adds no value.

Operate existing sources repeatedly using their configured engines. Maintain the
source's operational runbook and report verified progress with counts and reasons.
This skill guides an invoked agent; it does not install a scheduler or stay running
between invocations. AWS acquisition supplies completed deliveries independently.
OpenMetadata's catalog `Pipeline` entries describe those workflows; they do not
start or resume Bookkeeping runs. Use [the OpenMetadata execution boundary](../openmetadata/SKILL.md#pipeline-execution-boundary)
when deciding whether an installed catalog can control operations.

## Start with live state

Resolve the requested environment, source and retained delivery from existing
configuration and evidence. Reuse the current authorization for that scope.
Read the source's runbook and live Bookkeeping runs/leases before starting work;
another agent's in-flight work is a dependency, not a cleanup target.

Use [RUNBOOK.md](RUNBOOK.md) for last-run lookup, delivery, file-change, capacity and recovery.
Discover actual command capabilities with `edgar-warehouse doctor` and
CLI help. Report missing enforcement or unsupported stages as runtime gaps;
instructions cannot make them available. An offline sequence check is not a
runtime readiness certificate. To install, enable and run one source, then
clear a finished test, follow **Install and enable one source**. To load a
captured delivery, use **Load a capture**: one command for every source. Recover
retained progress before making a new run.

When deploying tested configuration to an environment, follow **Configuration
promotion** in RUNBOOK.md. Reuse the existing Rules approval procedure and exact
release evidence; distinguish an approved release from its active deployment.
For timing reports, use the [five-minute workflow](TIMING-REPORTS.md).

## Apply store DDL

This skill applies DDL. Read [STORES.md](STORES.md) before creating or changing a store's schema, or applying an approved silver spec, on any engine.

## Operationalize every domain

Do this after the five schemas are current, for every domain. A domain is one
source directory under `rules/sources` together with every entity kind that
source's merge policy names. Walk all of them. Two named kinds are not
the whole list.

1. **Stores.** Confirm the five schemas in **Apply store DDL** and Rules are
   current on the selected engine. Route a dialect refusal as missing engine
   support; retain that target's blocker while independent targets proceed.
2. **MDM, per domain.** Follow **Configuration promotion** in RUNBOOK.md for
   that source and its merge policy. Read back the active version. A domain
   whose source or policy is still a draft, or whose activation is refused,
   stays blocked. Record the refusal and go on to the next domain. Loading
   entities waits until that version is the active proven one.
3. **RDM, per domain.** A new store's RDM is empty: restore every published code set from git with
   `scripts/rdm_restore_published.py --by <name> --words "<their exact words>"` in this skill
   (with the runtime connection from [Connection URLs and environment](../data-platform/SKILL.md#connection-urls-and-environment);
   it drafts, approves in those words, publishes and checks each version's sha256
   against its `pin.json`, and exits 1 naming any that differs). Then `edgar-warehouse rdm list`, then
   `edgar-warehouse rdm describe <code set>` for every code set that domain
   pins. A published version is operational. A missing or draft code set is a
   blocker for that domain: route it through data-profiling's RDM steps
   (`rdm draft`, `rdm diff`, operator `rdm approve`, `rdm publish`). Leave the
   code set unpublished until those words exist.
4. **Apply the silver spec.** This skill applies DDL. Data-profiling writes
   the logical spec and does not. MDM engineering writes the MDM store's own
   migrations and does not apply a profile's silver spec.
   For each part with an approved spec, apply that spec to the selected Silver
   engine, using the connections in the central section above. On PostgreSQL or MySQL,
   `edgar-warehouse silver register <findings.yaml> --part <part> --runtime-role <role>`,
   then `edgar-warehouse silver describe <table>`. Numbers, identifiers and
   material commentary are the fields the spec already names. The same spec
   is the logical input for MySQL and SQL Server Express as well. Silver
   registration supports PostgreSQL and MySQL; SQL Server is deferred. Qualify
   the selected engine's normal registration, not only its compiled table.
   Registration must compile the spec through
   [sql-writer](../sql-writer/SKILL.md) and install the table, registry,
   comments and restricted grants through a recoverable registration path.
   Report success only after all of them read back correctly. A standalone compiled table
   leaves registration incomplete. A part with no approved spec, or a pipeline silver step
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

Read [STORES.md](STORES.md), "Qualify Silver storage", before declaring a Silver store ready on an engine.

## Install and enable one source

Read [INSTALL-SOURCE.md](INSTALL-SOURCE.md) when the task is to load and master one Rules source before the next.

## Load a capture

One command loads a captured delivery through one source's target, from
start to finish. It knows no source, target or store by name. Everything
comes from the rules files and the stores folder you give it.

```bash
edgar-warehouse load \
  --source <source> --target <target> \
  --capture <capture folder> --capture-run <capture run id> \
  --stores <stores folder> \
  --workers <readers> --bundles <runs at once> --minutes <window>
```

- `--stores` is the stores folder configured through
  [Connection URLs and environment](../data-platform/SKILL.md#connection-urls-and-environment).
- **Create a store from an up-to-date checkout, and keep its lifecycle there.** `up` refuses a checkout
  behind `origin/main`, and a store belongs to the checkout that created it: `up`, `stop`, `backup` and `copy`
  from another checkout stop at "Environment belongs to another worktree". A stale untracked skill link
  blocks fast-forwarding the main checkout; remove the link (not its target) first.
- Add `--fact name=value` and `--file name=path` for each input the target's
  `run` declares; `scripts/run_inputs.py <source>` in the data-onboarding skill lists them.
- **A target that lands silver registers its tables itself**, before it submits
  anything, as the migration login configured through the central connection section
  (the same spec again changes nothing). Do not register by hand first.
- **Look on the machine before asking to capture.** Reading retained files needs no provider request, so search
  every place below before asking for one. Say which you found: a cohort proves a path, never a delivery's totals.
- **The engine reads no gzip.** A folder of `.gz` files stops as "malformed": unzip a copy, then write its receipts.
- **A capture left by `provider.capture` has no `receipts.jsonl`.** Run
  `scripts/capture_receipts.py <capture folder>` once: it writes one receipt per
  file and never replaces a receipts file.
- **A reload whose inputs changed needs `--revision N`** (default 0, the
  first publication). A changed input (a new Name Matching, say) changes a record under the
  same revision, and the Stage refuses it ("Source native revision has
  contradictory publications"): pass a revision higher than the last load's
  (the bundles all stopped at merge until it was raised).
- **A source's Bookkeeping section must be version 2.** `load` cannot plan a
  version 1 section: every bundle stops at `mdm prepare-capture` with "must be
  version 2" before any run is submitted. Check
  `grep -A2 '^bookkeeping' rules/sources/<source>/source.yaml`. A source still
  on version 1 has its own route (see that source's doc) until it is converted.
- **Plan first.** Add `--plan` (no `--capture-run` needed) before claiming or
  starting a load. It changes nothing and prints which open runs `load` would
  finish, which it would leave and why (a run pinned to old worker code is
  left, and its documents load again in a new run), a blocked run that would
  stop it, and the documents and bundles. One load spent an hour on 14 open runs
  that the plan shows as pinned in one call.

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
   queue. A bundle that stops does not stop the others. Once `--minutes`
   has passed no new bundle starts, and every stop is named at the end. The Change Journal leaves out documents already loaded under
   these rules. Already-loaded documents are counted and skipped, and an
   unchanged rerun starts no work. "These rules" are the source's own rules and the part of the merge policy that
   acts on it (its rules, their identifier contracts, the kind's field defaults), so a rule of another source does
   not load its documents again. If a bundle says `512 of 512 documents to load` when you expected `already loaded`,
   something in that slice changed: find what before the load spends hours.
   **Force publish** (`load --force`) is the explicit exception: it ignores the Change Journal and processes every
   document of the source again, as a new publication of the capture run (`<run>+force-<time>`); the journal records
   it as forced. Use it when the result must be made again whatever the journal holds (after `mdm clear-source`,
   or to rebuild from retained files). Never for a daily run.

It prints one line per bundle as it goes. At the end it prints a JSON
summary: documents loaded, documents already loaded, and each run's id and
counts.

**Stopping is safe.** A deadline, a closed laptop or a failed unit leaves
the run resumable. Run the same command again. It finishes the open run
first and never loads a document twice.

### Derive a run input; never ask for what the store can decide

Declared `preparation` operations finish before derived files or new bundles, under the selected worker login.
They require the current source Rules digest to be active. Complete-set matching may expand the next read's
scope; binding still follows identifier matching. Reuse a hash-bound cached projection only for identical bytes,
population, recipe, policy and runtime; an unchanged repeat applies nothing. Keep a completed projection
for retry after interrupted application. EOF and count verify the declared complete scope; independent
provider completeness needs publisher evidence.

A target's run files and facts are of two kinds: what the caller must bring (a capture, a time, a count the
provider states) and what the rules and the store decide (a scope, the names a reading keeps, a list that flags
nothing). The second kind is declared in the target's `run.derived` with a registered method, its `purpose` and its
`why`, and the loader builds it on every load, go-live or daily, from what the store holds then.

- **Never ask the operator for a derived file.** Ask only when neither the rules nor the store can decide, or a
  ruling is new, and then ask once, record the ruling in the rules, and let the loader apply it from then on.
- **A new derived input is one registered method and one declaration** with its purpose and why, tested on invented
  records; the load says what it derived, how many values and why.
- **The caller can still give the file** (`--file name=path`): a given file wins over the derived one.

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
rest are set aside by its classification), not the Companies; GLEIF finds Companies and never creates one, and
the SEC Companies pair with GLEIF through the waterfall pass. A Security is mastered from OpenFIGI, N-PORT
securities and 13F securities in the same way.

### Examples: where retained files are

Under `~/.local/share/edgartools/mdm/`, `captures/` holds whole deliveries and `proving/` holds cohorts:

| Feed | Folder |
|---|---|
| Company facts | `proving/company-facts/` |
| ADV | `proving/p07/inputs/warehouse/bronze/reference/iapd_adv_bulk/` |
| 13F and ownership, by CIK | `proving/p07/inputs/warehouse/bronze/filings/sec/` |

`~/edgar-local-tmp/` holds working copies from earlier tests.

### When it stops

| You see | It means | Do this |
| --- | --- | --- |
| `workers work <operation> ... failed with status 1; its message is in <log>` | A worker could not finish a unit. | Read that log (`load-errors.log` in the stores folder), fix the cause, and run the same command again. The unit is tried again first. A transient database error (a deadlock, a closed connection) clears on that retry. A retry that fails the same way ("Artifact hash mismatch": an earlier run left a different file at the output path) cannot be resumed: `load` names that run, leaves it as it is and loads its documents again in a new run from the Change Journal. Give each load its own `--as-of` (the default is now), because the output folder is named by it and a reused one collides with an earlier run's files. |
| `step <s>: unit <u> failed (<error>)` | A unit failed and is still failing. | Run `bookkeeping status <run> --step <s>` to see its error, fix the cause, and run the same command again. |
| `Run <id> of <source> <target> is blocked` | Bookkeeping stopped that run, frozen under the active rules version, on corrupt or missing evidence. `load` will not submit its documents again. | Read `bookkeeping status <id>` and recover it ([recovery](../bookkeeping/RECOVERY.md)), then run the same command again. |
| `did not finish before the deadline` | `--minutes` ran out. | Run the same command again, or give a longer `--minutes`. |
| `declares no <target> target` | No target of that name in `rules/sources/<source>/source.yaml`. | Use a target listed there. `rules sequence check --source <source>` names the wired one. |
| `ended waiting` or `ended blocked` | `finalize` found a check that did not pass. | Read `bookkeeping status <run>` (its `run.checks`) and the run's errors. Never submit the bundle again. |
| `all N documents already loaded` | The Change Journal holds every document of that bundle under these rules. | Nothing to do. Rerun with changed rules or new files only. |

A unit left `waiting` with `Lease or prerequisite contention; retry on
resume` is not a failure: a worker found its prerequisites or leases busy.
`load` claims it again on the next pass, and waits a few seconds when a pass
moved nothing (a lease from a stopped worker has not expired yet).
(`bookkeeping resume` resets only the run's state, not such a unit.)

An open run is driven by the steps it was frozen with, so a later rules
version never changes a run already under way. Two kinds of run are reported
and left as they are, and their documents load again in a new run (the Change
Journal never recorded them): a blocked run frozen under a retired rules
version, and an open run pinned to other worker code, which no later checkout
can finish ("Pinned worker runtime changed; start a new run").

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

The operator names the window. A plan that does not fit it is not the plan
(operator: "10 hours will never fly must be within 1-2 hours").
Work it out from counts before starting:

1. **Documents and bundles.** Count the documents not yet loaded, and divide
   by `execution.max_artifacts`.
2. **Wide and narrow steps.** A wide step has one unit per file or group
   (`source.read`). A narrow step is one unit per bundle (`mastering.merge`,
   `mdm.prepare`). Only more bundles at once shorten narrow steps in total.
3. **Bundles and readers.** `--bundles` is how many runs go at once and
   `--workers` is the worker processes on each step of a run; each worker
   checks its own units. Keep `--bundles` × `--workers` near the
   core count. `load` never starts more workers than a step has units left.
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

   **Problem:** merges that had saved all 52 batches still died, with no
   receipt (9 of them). **Root cause:** after the saves, the receipt, the
   resumed-start check and the run report each read every saved batch's intent
   and publication payload at once (2.7 GB of intents for one bundle; 9.5 GB
   peak footprint, so swap and a kill). **Fix:** they read one batch at a
   time (receipt 493 s to 29 s, 1.7 GB). **Lesson:** a failed merge may have
   saved everything, so count its applied batches before blaming the saves;
   and a rerun of a saved merge only writes the receipt, so it measures
   nothing about saving. Measure a merge that has never run.

### While a load runs

- **Finish open runs with `load`, never by hand.** `load` finishes what is
  open and runs the later steps. Driving `workers work`
  yourself skips the later steps, and a bare `--reports`
  path (it needs a `file://` address) marks the unit `waiting`.

- **Leave worker code alone** (`edgar_warehouse/workers/*`). A run pins its
  worker runtime and stops on a change ("Pinned worker runtime changed;
  start a new run"). Change code between loads.
- **Size the lease to the slowest claim, not to the work.** A step that
  reads another run's output rechecks that run on every claim and report,
  which can outlast the default 120 s lease ("Stale lease"). The target sets
  `lease_seconds` and `heartbeat_seconds`.
- **A long run shows its progress.** Sample any run over ten minutes in its first two minutes with
  `scripts/dev/run_sample.py`. Send its output to a file, unpiped: a `| tail` hides a slow page until the run ends. A
  build with no progress line gets one before it starts.
- **Check every 30 minutes, not in a tight loop** (operator).
  A check that finds nothing changed sends no message. Report a failure, a
  finished bundle or the end.
- **Keep the machine awake and on power.** Sleep stops the workers. Their
  leases expire and the units run again later, with nothing loaded twice.
  On macOS, check `pmset -g` (`sleep`): while the machine sleeps, Docker,
  every test container and the shared server freeze, and brief Power Nap
  wakes make a run look slow, not stopped (a 6-minute test took 61, ticket
  138). Start a long run or test as `caffeinate -i <command>`.
- **Measure a slow load with `scripts/profile_load.py`, never by hand**.
  `progress` shows, for the running runs, the units in each state per step and how long they have run: the
  answer to "how far is it", and it lists runs left `running` by a load that was stopped.
  `quality` lists the data quality counts each merge run retained (records, records set aside by a failed check,
  open reviews, fields with empty values).
  For a completed run whose frozen steps requested version-2 silver quality evidence,
  `edgar-warehouse rules catalog publish --bookkeeping-run <run-id>` sends only
  verified per-unit outcomes with stable run, step and opaque unit references,
  then requires exact timestamped OpenMetadata readback. Use
  `edgar-warehouse rules catalog check --bookkeeping-run <run-id>` for a
  read-only confirmation later. An incomplete run remains unknown and cannot
  publish. The publish reconciles the whole catalog plan, not only the quality
  results: run it from a checkout at current `origin/main`, or it removes
  catalog objects the current rules describe. The quality results themselves
  are keyed by timestamp and survive that reconcile. Keep `SILVER_QUALITY_EVIDENCE_V2` unset until
  [Enable a new receipt format](../bookkeeping/RECOVERY.md#enable-a-new-receipt-format)
  is met. Catalog
  entries describe the load and its checks; OpenMetadata does not run or resume
  the pipeline.
  `failures` groups the units that hold an error by step, state and error shape, with counts: read it before
  opening the load log.
  `steps` gives each step's share of a finished run;
  `sample` ranks what the database ran, once a second. Configure profiling connections through
  [Connection URLs and environment](../data-platform/SKILL.md#connection-urls-and-environment).
  For a statement inside a function, set `shared_preload_libraries=auto_explain` with
  `auto_explain.log_nested_statements=on` and read the server log. The first answer is the step; the second,
  the statement.
- **Read a failed call's database error**, the `(psycopg2.errors.X)` line,
  not SQLAlchemy's last line, which is only a link.
- **A target that reads another target's runs** (`{run: {source, target,
  step}}`, [Bookkeeping SPEC](../bookkeeping/SPEC.md)) loads after that
  target. The comments in `rules/source-sequence.yaml` give the order.

### Underneath `load`

`load` runs the same steps you can run by hand when diagnosing: `mdm
prepare-capture`, `rules run`, `workers work <operation> <run>` (several in
parallel; a lease keeps two off the same unit), and
`bookkeeping finalize <run>` ([Bookkeeping run](../bookkeeping/RUN.md)).
Do not write a source-specific driver script. A missing step is a gap in `load`: fix it
there.

## Operate the recurring loop

1. **Inventory and readiness.** Account for the entire declared delivery and its
   acquisition completion evidence, expected/available file counts and receipt
   hashes. Check approved processing versions and required references. An existing
   folder or timestamp alone cannot establish downloaded-and-ready status. Let
   independent ready sources proceed when another source is delayed; hold only
   genuinely dependent work. Never start acquisition to resolve a missing delivery.
2. **Changes.** Compare with the last verified inventory and consult the Change
   Journal under the actual processing identity. Distinguish new bytes, changed
   rules/shared inputs, suspected renames and schema drift using RUNBOOK.md. Route
   new feeds to [data-onboarding](../data-onboarding/SKILL.md), shape/meaning changes
   to [data-profiling](../data-profiling/SKILL.md), and existing rule changes to
   [refining-rules](../refining-rules/SKILL.md). Routine deliveries reuse applicable
   qualification and approval; missing version evidence is reconciled, not invented.
3. **Size the work.** Measure usable CPU, memory, disk, database connection budget
   and competing work at the actual execution host/container. Fit the load into
   the window (**Load a capture**) before choosing `--workers`. Use prior verified measurements and current supported bounds to choose
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
