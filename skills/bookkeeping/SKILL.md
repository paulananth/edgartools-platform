---
name: bookkeeping
description: Initialize or migrate Bookkeeping, or plan, validate, run, inspect and recover work through loader-independent control and its worker task protocol. Enforce separation of worklists, leases, checkpoints and verified evidence from external workload execution and destination verification. Source interpretation belongs outside Bookkeeping.
---

# Bookkeeping

> Part of the **data-platform** skill, installed as one package with its
> commands. Start there for setup (install, stores, `edgar-warehouse doctor`)
> and for the whole flow; this skill holds one step's detail.

**Modes:** init, migrate, plan, validate, run, status, recover. Bookkeeping
owns work control and verified completion. Workers, each in its own process,
own the work itself. `edgar-warehouse rules run` submits the approved versions;
workers then pull the work (`edgar-warehouse workers work`), each checking
its own result once, and `edgar-warehouse bookkeeping finalize`
delivers control's events and records the run's checks. There is no
`bookkeeping run` command (operator: "Keep `rules run`"). Plan,
validate and recover are steps you follow with the existing commands; they are
not commands of their own.

## Required independence

Bookkeeping must operate without any loader or domain implementation installed.
Its control process, CLI construction and helpers must not import, instantiate
or call loaders, parsers, Silver/MDM implementations or source-specific
execute/reconcile/verify callbacks. Passing the whole Bookkeeping object to an
external operation also violates this requirement. Moving a callback to another
file or selecting its name in YAML does not remove the dependency.

Use a fixed task protocol with immutable specifications and references. External
workers execute and reconcile effects and check their own results.
Bookkeeping owns dependencies, leases/fencing, retries, checkpoints, evidence
admission and control outbox delivery. Source/feed names are opaque selection
metadata; source grammar and domain checks stay outside control.

Read [INDEPENDENCE.md](INDEPENDENCE.md) before planning or changing an execution
path, validating its architecture, or running/recovering it under this contract.
It defines the evidence required to claim independence and what is built so
far. The callbacks are gone (mastering to-do 20a); never add one back.

**Use another skill when:**
- a feed is new: use **data-onboarding**;
- a live feed's mapping, quality or matching rules change: use
  **refining-rules**;
- recording or recovering journal delivery: use **change-journal**.

Use the shared engine in `edgar_warehouse/bookkeeping/clean/`. It retains
control references and evidence; source records stay in their owning stores.
The currently implemented protocol and supported boundaries are in
[the specification](SPEC.md).
The design is linked from INDEPENDENCE.md; its status there says which gates
have run. Existing CLI syntax is not proof of loader independence.
`edgar-warehouse` is the installed data skill bundle (see the **data-platform** skill, Setup). In a checkout of the repository, put `uv run --extra mdm --extra s3` in front of it instead.
Run `edgar-warehouse doctor` first; it checks that every command here exists.

## Invocation and required inputs

```text
$bookkeeping plan --source <source> [--feed <feed>]
$bookkeeping validate --source <source> [--feed <feed>]
$bookkeeping run --source <source> [--feed <feed>]
$bookkeeping status <run-id>
$bookkeeping recover <run-id>
$bookkeeping init
$bookkeeping migrate
```

These are **skill arguments**, not warehouse CLI commands. Plan, validate and
run name the source; they name a feed only for live acquisition (a run over
files already captured names none). Init and migrate operate on the whole
fresh control store, so they do not take source or feed. Preserve values already
provided in the conversation; ask for missing source or feed only when a
feed-scoped mode needs them. Additional inputs are a target/stage range,
environment, bounded input references and,
for continuation, a run id. Infer those when the request or retained evidence
settles them; ask only when the choice changes the intended work.

Resolve `source` to an existing Rules document, accepting a provider name only
when the repository identifies its source document unambiguously. Resolve
`feed` only from an active `acquisition.feeds` declaration, and only for live
acquisition: a run over captured files names no feed and needs only the
version's test-run proof and approval. Read documents through
`edgar_warehouse.rules.files`.

### Source registration and pipeline discovery

For a source inventory or source-to-domain trace, account for every folder in
`rules/sources/`: each needs its matching `source.yaml`, a `bookkeeping`
declaration with the intended target and step graph, and an entry in
`rules/source-sequence.yaml`. Treat a missing declaration or sequence entry as
an onboarding gap, not an implicit default. A sequence entry with
`target: null` is inventory-only and has no registered source target; do not
report it as runnable through Bookkeeping. The sequence's `after` value is
preferred ordering, not a step dependency or a request to run that source.

A target is written in one shape, and the steps follow from it
(`edgar_warehouse/rules/shape.py`):

```yaml
<target>:
  extract: record.yaml           # the source's last rules file; several when silver lands from another
  master: {keys: {table: <table>, record_column: record, dataset: <dataset>}}
  silver:
    - {name: land_facts, land: {table: <table>, silver: <silver table>}}
```

Each rules file says what it reads in its own `pass` block, so the passes
follow from the files:

```yaml
pass:
  files: "*.zip"                 # a read: which captured files, its units and context
  units: {each: file}
  lookups: {filed: {from: dates.yaml, table: filed, column: id, value_column: filed}}
---
pass: {readings: {rows: {all: rows.yaml}}}     # a join: the rules files it joins
---
pass: {pieces: {step: join.yaml}}              # the record: the join it reads over
```

A pass is named after its file (`row-counts.yaml` is `row_counts`) unless the
block names it; the source's own `source.yaml` always names its pass. A pass
waits for the files it names, so no target writes a wait, a key, a lease, a
check or the record step. The engine reads a rules file without its `pass`
block. Mastering reads the last pass whole unless `master.readings` says
otherwise. `capture: copy` or `capture: provider` is a target that only brings
files in; `record: false` is a second pass over files another target records.
Writing a target another way that gives the same steps loads no file again;
renaming a pass or changing what it reads loads the source once more.
Before a change to a target merges, run each source's end-to-end tests on
local PostgreSQL (`scripts/dev/adapter_test.sh`), one result per source.

To trace a source into a domain, read its `dataset_contracts` and follow
their declared kinds to the merge rules. Then follow the source's
`bookkeeping.targets` steps, inputs, operations and prerequisites to their
outputs. Trace any RDM code sets and Silver table specs as separate configured
paths; neither store is an automatic stage in every target. Confirm each
operation's worker profile is implemented before calling the target
executable. A registration or catalog plan proves configuration only; run
completion requires the validated run and admitted verification evidence in
this skill's **Validate**, **Run** and **Result** modes.

For live acquisition only, resolve the feed binding deterministically first:

```bash
edgar-warehouse plan resolve-feed --source <source> --feed <feed>
```

This read-only helper returns the Rules digest, exact dataset/member set and
available targets. It does not validate input membership or authorize a run;
verify those against captured source manifests in the chosen mode.

Keep source, feed, resolved document/datasets and target in the plan and
validation evidence. Bind the selected feed in frozen worklist control keys
and verify input artifacts belong to those datasets/publications. The runtime
uses `--source <resolved-rules-name>` and `--target`, and an explicit `--feed`
only for a live acquisition run.
Recover a run only after its retained manifest proves the same source/feed.

Confirm live commands with `edgar-warehouse bookkeeping --help` and
`edgar-warehouse rules run --help`.

### The task protocol

A step's `operation` names the **worker profile** that pulls it. The profiles are `artifact.copy`, `source.read`, `source.combine`, `mdm.prepare`, `mastering.merge`, `provider.capture`, `journal.record`, `silver.land` (a reading's table into a registered silver table, checked by asking silver for the unit's own keys) and `silver.derive` (a silver table built from other silver tables, checked by reading it back against a receipt of its keys). Workers
reach Bookkeeping only through these commands, which print JSON:

| Command | Who calls it | What it does |
|---|---|---|
| `bookkeeping claim <run> --profile P --limit N` | worker | Claims units and prints task envelopes |
| `bookkeeping renew --envelope -` | worker | Renews the lease while the work runs |
| `bookkeeping report --envelope - --candidate URI --sha256 H --checks URI --checks-sha256 H` | worker | Completes the unit: its output and the worker's own check report, bound to that work, with every check the step names. The first report pins the profile's runtime for the run |
| `bookkeeping fail --envelope - --message M` | worker | Gives the attempt up; the unit waits |
| `bookkeeping finalize <run>` | operator | Delivers control's events and records the run's checks |
| `bookkeeping grant-profile --profile P --worker W` | operator (migration owner) | Lets login W work profile P's steps |

A worker connects as its own login, with the restricted control runtime grants.
A profile no login was granted cannot claim or complete anything. A profile
group records authenticated membership; it carries no SQL object privileges.
Control is also packaged alone: `packages/bookkeeping` (`edgar-bookkeeping`).

`edgar-warehouse workers work <profile> <run> --reports <uri>` runs a worker. The profiles built are the keys of `PROFILES` in
`edgar_warehouse/workers/__init__.py`; `edgar-warehouse workers describe <profile>`
shows one. A step whose profile is not there has no worker yet: report its
execution as unsupported; never route it through an in-process callback.

Each profile has one `check` of what it wrote, run once by the worker before
it reports. A step that writes a destination (`mastering.merge`, `silver.land`,
`silver.derive`, `journal.record`, `provider.capture`) reads the destination
back. `source.read` and `source.combine` check that the output names this
contract and these inputs and holds only declared tables; `mdm.prepare` checks
each records file against the hash its manifest states. Bookkeeping pins the
worker's runtime per run and hashes the input and output.

A target marked `local: true` runs its `source.read` and `source.combine` steps in the loader's own process
(`rules/local.py`, called by `rules run`). They take no claim, lease or heartbeat and write files with
receipts, and the content hash is their proof. The run in the database starts at the first later step
(`config.staged`), with those receipts as its inputs, and Bookkeeping holds no record of the local steps. A local step requires only local steps, and a
local step that generates work is refused until a source needs it.

## Init and migrate modes

Use `init` for an empty Bookkeeping database on PostgreSQL 16 or MySQL 8;
use `migrate` only for its already initialized, checksummed storage.
Both install the selected engine's frozen migrations and refresh restricted runtime grants.
`migrate` refuses to create a missing schema; checksum drift or an untracked
schema blocks both. These modes create no run, import no legacy history or
checkpoints, and do not change Rules, Change Journal or destination schemas.

Select the migration-owner connection through
[Connection URLs and environment](../data-platform/SKILL.md#connection-urls-and-environment)
and pass an existing restricted runtime role. Never use the runtime login as
the migration owner. Check the configured database, selected engine/version
and role before executing; do not print connection secrets. Then run the
selected command and verify the returned migration checksums, five control
tables, runtime privileges and zero imported run/work rows:

```bash
edgar-warehouse bookkeeping init --runtime-role <role>
edgar-warehouse bookkeeping migrate --runtime-role <role>
```

The database defaults to `bookkeeping`. An explicitly approved different name
uses `--database-name <database>` on either command; the selected owner must
target that exact database. Driver setup is in the central connection section.
Keep the existing runtime account's host restriction: MySQL resolves its unique
account and refuses ambiguous same-name accounts rather than widening access.

MySQL's incomplete migration marker refuses normal writes, including cached
callers. Repair an interrupted installation with the same build, then rerun
`migrate` for each configured runtime principal to restore its grants. Missing
initialized tables or changed installed guards/indexes require owner diagnosis
and restoration; migration does not replace lost control history with empty data.
Qualify populated recovery, both duties, actual index use and completion delayed
past lease expiry. Compare the exact retained receipts/cursors, not just counts.
SQL Server's normal control lifecycle remains deferred; its existing read and
prepared-transition helper checks do not qualify a whole run.

Select one command for the requested state. Caller-held destination transaction
guards are PostgreSQL-only. When those guards are in scope, provision them
separately with `bookkeeping init-guard` and its restricted destination role,
using the destination-owner setup in the central connection section.
MySQL writers use their destination's own atomic capability; report unsupported
legacy guard calls explicitly rather than emulating deferred commit enforcement.
Neither control-store mode silently provisions a destination or executes work.

## Plan mode

Skip plan and validate for a target whose active Rules version and worker
profiles are unchanged since its last verified run: run it. Plan and validate
only what changed.

Read the selected feed's captured manifests, existing stage code and control
configuration. Preserve source mapping/policy and stage order. Prepare the
intended `bookkeeping` section and a version 2 manifest: every configured step
has a separate bounded worklist, exact URI/lowercase SHA-256 references, and
predecessor selectors naming declared prerequisite step/key identities.
Source records stay in artifacts. Lease scopes name actual conflicting work
or write resources; a feed label alone does not prove the right conflict scope.

Audit the control dependency path first using INDEPENDENCE.md. Plan external
worker profiles and frozen specification references; do not add a
source-specific capability to the control registry to fill an execution gap.
Record missing task-protocol support as required implementation work.

Write a reviewable plan bundle in the current workstream: source/feed binding,
resolved datasets, target, proposed Rules body/digest, manifest/reference and
hash, expected counts per stage, processing versions, lease/check declarations,
publication/delivery requirements, retry/resume behavior and capability gaps.
For continuation, reference the original frozen bundle instead of changing it.
Use captured files and read-only inspection; planning does not activate Rules,
submit work or deploy infrastructure. Done means the full requested scope is
accounted for, including explicit blockers, rather than a claimed executable
plan with unsupported stages omitted.

## Validate mode

Load the plan for the same source/feed. If missing, prepare it through plan
mode first. Pin its hash and validate the exact proposed Rules/configuration,
worklist scope and input hashes with the implementation validators. A later
configuration, input or processing-version change invalidates this validation.

Validate loader independence separately from source output correctness using
INDEPENDENCE.md. A unit is complete only when Bookkeeping accepts its
worker's check report.

Use bounded captured inputs and isolated PostgreSQL 16 control/destination
stores for actual execution. Verify the selected feed's stage outputs,
accounting, receipts, required publication and journal delivery. Exercise
interruption/resume, lost acknowledgement, duplicate delivery, prerequisite
holes and stale-worker rejection appropriate to the changed stages. Run the
configured contract tests and mandatory
`tests/integration/test_configured_bookkeeping_postgres.py`; prerequisite
failures are failures, not qualifying skips. A generic suite alone does not
prove the selected source/feed worked.

Produce validation evidence containing the source/feed binding, plan/config/
manifest hashes, processing versions, sample bounds, actual run/receipt
references, expected/verified counts, check/delivery results and remaining gaps.
Only mark the requested scope passed when its required work and verification
were exercised successfully. Partial validation stays explicit and cannot
qualify the omitted stages for a run. Validation executes isolated samples;
it does not activate live Rules, publish to live destinations or perform AWS
cutover. This is Bookkeeping validation, not the unfinished Rules Batch Gate
evaluator, and does not grant a person's MDM approval.

## Run mode

Read [RUN.md](RUN.md). Apply the validated configuration and submit or
resume its bounded run in the selected environment. Verify that the plan,
validation evidence and frozen inputs still match the requested source/feed.
The run freezes the rules files it is given. Submit
with `rules run`, then run each step's worker and finish with
`bookkeeping finalize` (see RUN.md). A step whose profile has no worker yet is
unsupported: report it, and do not invent a command.
Infrastructure rollout belongs here only when explicitly included in the user's
run request and independently qualified.

## Status mode

```bash
edgar-warehouse bookkeeping runs --limit 20
edgar-warehouse bookkeeping status <run-id> --limit 100
edgar-warehouse bookkeeping checks <run-id>
edgar-warehouse bookkeeping leases <run-id> --limit 100
```

Use the runtime connection selected through the central connection section.
`status`, `checks` and `leases` take the run id; `runs` lists them. `status` also returns
`failed_steps`, the distinct step names with a waiting work item, a recorded
attempt and an error. This aggregate omits unit keys and error text; do not copy
`items[].error` into OpenMetadata.

## Recover mode

Read [RECOVERY.md](RECOVERY.md). `edgar-warehouse bookkeeping resume <run-id>`
reopens the run (exit 3 means it is not complete yet); then run the workers
again. A completed unit is not checked again. A worker
reconciles an earlier attempt's effect before writing. Delivery to the Journal
of a run's committed events is the Change Journal skill's **recover-delivery**.

## Result

Report mode, source, feed, resolved target, bundle/run references, commands,
verification and concrete remaining gaps. Record unsupported commands and
operational assumptions in the current workstream's log. Never present a plan
as validation, or isolated validation as a completed live run.
