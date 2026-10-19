---
name: data-operations
description: Operates every domain and applies the DDL for MDM, RDM, Bookkeeping, Change Journal and silver on PostgreSQL, MySQL or SQL Server Express. Use when making those stores operational, applying a schema or an approved silver spec, operating daily loads, checking source readiness, managing a backlog, monitoring a run or maintaining its operational runbook.
---

# Data Operations

Work lean: check each step against [the seven wastes](../data-platform/SKILL.md#the-seven-wastes) and drop what adds no value.

Operate existing sources repeatedly using their configured engines. Maintain the
source's operational runbook and report verified progress with counts and reasons.
This skill guides an invoked agent; it does not install a scheduler or stay running
between invocations. AWS acquisition supplies completed deliveries independently.

## Start with live state

Resolve the requested environment, source and retained delivery from existing
configuration and evidence. Reuse the current authorization for that scope.
Read the source's runbook and live Bookkeeping runs/leases before starting work;
another agent's in-flight work is a dependency, not a cleanup target.

Use [RUNBOOK.md](RUNBOOK.md) for delivery, file-change, capacity and recovery
decisions. Discover actual command capabilities with `edgar-warehouse doctor` and
CLI help. Report missing enforcement or unsupported stages as runtime gaps;
instructions cannot make them available. An offline sequence check is not a
runtime readiness certificate. To install, enable and run one source, then
clear a finished test, follow **Install and enable one source**. Recover
retained progress before making a new run.

When deploying tested configuration to an environment, follow **Configuration
promotion** in RUNBOOK.md. Reuse the existing Rules approval procedure and exact
release evidence; distinguish an approved release from its active deployment.

## Apply store DDL

This skill applies DDL. Data-profiling writes a logical silver spec and does
not. MDM engineering writes the MDM migration files and does not apply a
profile's silver spec.

Use the operator's selected engine for each store: PostgreSQL, MySQL or SQL
Server Express. Resolve the connection's dialect and verify it matches that
selection before writing. For an all-three request, track each engine's
schema and domain state separately. Connectivity alone proves no schema or
merge capability. Preserve the selected engine when a command refuses it;
route the missing implementation to its owning engineering work instead of
substituting PostgreSQL.

Apply these five schemas into databases that
[data-platform](../data-platform/SKILL.md) already created: `mdm`, `rdm`,
`bookkeeping`, `change_journal`, and `silver`. This skill does not create
the databases or the engines. Read each command's `--help` before the
first use. The required initialization path uses the same logical schema
and supported command interface with a storage adapter for the selected
engine. [sql-writer](../sql-writer/SKILL.md) compiles portable tables and
queries; the migration owns installation, grants, checksums and readback.
MDM's shared merge behavior and storage-adapter requirements belong to
[MDM engineering](../mdm-engineering/SKILL.md#database-agnostic-merge-logic).

**Current implementation gap:** the five commands below currently implement
PostgreSQL 16 only. MySQL and SQL Server accept connections but their store
initialization is missing. This is an implementation defect against the
selected-engine contract, not a restriction on the operator's database choice.
Record the exact missing capability and leave that target incomplete until
its migration, runtime operations and restricted-role checks pass. Creating
some tables or translating SQL does not establish a working store. Apply
the same capability check to Rules setup through data-onboarding.

| Schema | Command | Owner connection |
|---|---|---|
| MDM | `edgar-warehouse mdm migrate --application-role <role>` | `MDM_DATABASE_URL` |
| RDM | `edgar-warehouse rdm init --runtime-role <role>`, then `rdm migrate` | `RDM_MIGRATION_DATABASE_URL` |
| Bookkeeping | `edgar-warehouse bookkeeping init --runtime-role bookkeeping_runtime`, then `bookkeeping migrate`. The database name is `bookkeeping`. | `BOOKKEEPING_MIGRATION_DATABASE_URL` |
| Change Journal | `edgar-warehouse change-journal init --runtime-role <role>`, then `change-journal migrate`. The database name is `change_journal`. | `CHANGE_JOURNAL_MIGRATION_DATABASE_URL` |
| Silver | `edgar-warehouse silver init --runtime-role <role>`, then `silver migrate` | `SILVER_MIGRATION_DATABASE_URL` |

The runtime role exists, has no administrative privileges, and is not the
migration login. Done when the selected engine's migration history matches
the build, required objects and grants read back correctly, and restricted
runtime operations work. `edgar-warehouse doctor` shows the stores that
answer; it does not prove complete schemas or database-agnostic merging.

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
3. **RDM, per domain.** `edgar-warehouse rdm list`, then
   `edgar-warehouse rdm describe <code set>` for every code set that domain
   pins. A published version is operational. A missing or draft code set is a
   blocker for that domain: route it through data-profiling's RDM steps
   (`rdm draft`, `rdm diff`, operator `rdm approve`, `rdm publish`). Leave the
   code set unpublished until those words exist.
4. **Apply the silver spec.** This skill applies DDL. Data-profiling writes
   the logical spec and does not. MDM engineering writes the MDM store's own
   migrations and does not apply a profile's silver spec.
   For each part with an approved spec, apply that spec to the engine named
   by `SILVER_DATABASE_URL`. On PostgreSQL,
   `edgar-warehouse silver register <findings.yaml> --part <part> --runtime-role <role>`,
   then `edgar-warehouse silver describe <table>`. Numbers, identifiers and
   material commentary are the fields the spec already names. The same spec
   is the logical input for MySQL and SQL Server Express as well. `silver
   register` currently supports PostgreSQL only. The selected engine's
   registration implementation must compile the spec through
   [sql-writer](../sql-writer/SKILL.md) and install the table, registry,
   comments and restricted grants through a recoverable registration path.
   Report success only after all of them read back correctly. A standalone compiled table
   leaves registration incomplete. A part with no approved spec, or a pipeline silver step
   with no worker, stays blocked and is reported. `silver land` is the manual
   write until that worker exists
   ([data-onboarding](../data-onboarding/SKILL.md), Two targets).

A domain is operational when its MDM source and merge policy are the active
proven versions, every code set it pins is published in RDM, and every approved
silver spec is a registered table. Report one line per domain: operational, or
the blocker. The recurring loop below then loads that domain's entities from a
finished delivery. This section does not download, does not invent a command,
and does not mark a blocked domain complete.

## Install and enable one source

Use this when the task is to load and master one Rules source before the next.
The order and the run target come from `rules/source-sequence.yaml`. `after`
is preferred order only. `requires` is a real input dependency. One invocation
submits one source.

1. **Check the wiring.** Select that source alone:
   ```bash
   edgar-warehouse rules sequence check --source <name>
   ```
   Exit 0 and status `configured` means its `target` is a declared Bookkeeping
   target whose steps have workers. Exit 3 with `source_target_not_configured`
   means the source is not wired: report that and stop. Do not invent a target
   or submit a different source to stand in for it. A successful check does
   not install, approve or start a run. Detail is in
   `docs/specs/source-sequencing.md` in the repository.
2. **Install that source only.** Save its document into the Rules database.
   `rules load` saves every file under a root; do not use it here.
   ```bash
   edgar-warehouse rules save --source <name> --version <v> rules/sources/<name>/source.yaml
   ```
   Check it offline first with `edgar-warehouse rules check --source <name>`.
   Then test that version and record the test run with `rules record-proof`
   before any approval: data-onboarding's **test** step names the version
   label, runs `rules test` where the source's Bookkeeping section is
   version 2, and says what to use when it is not. A test that stops is not a
   proof and is not recorded.
3. **Enable it.** Follow [APPROVE](../data-onboarding/APPROVE.md). Activate
   the merge policy this source depends on first, then this source:
   ```bash
   edgar-warehouse rules activate --source <name> --version <v>
   edgar-warehouse rules status --source <name>
   ```
   Enabled means `rules status` shows that version `active`. There is no
   separate enable command.
4. **Wire the run.** Resolve the feed, then submit only this source and the
   target from the sequence check:
   ```bash
   edgar-warehouse plan resolve-feed --source <name> --feed <feed>
   edgar-warehouse rules run --source <name> --feed <feed> --target <target> \
     --input-manifest <uri> --input-sha256 <sha256>
   ```
   Work and verify as in [Bookkeeping run](../bookkeeping/RUN.md). The next
   source waits until `edgar-warehouse bookkeeping status <run_id>` shows
   `run.state` `complete` and every declared unit verified.

A test of this path, and how to clear that test, is
[Test and clear a source run](RUNBOOK.md#test-and-clear-a-source-run).

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
   and competing work at the actual execution host/container. Use prior verified
   measurements and current supported bounds to choose concurrency and bundle size.
   Account for verifier costs too. Unknown estimates start conservatively; exhausted
   resources wait. Size divides the whole backlog into work, never drops records.
4. **Submit or resume.** Use [Bookkeeping run](../bookkeeping/RUN.md) and
   [recovery](../bookkeeping/RECOVERY.md) for the existing task protocol. Keep the
   source-owned steps, original input/rule/reference/runtime pins and authoritative
   leases. Run declared local prerequisites only through supported approved paths.
   A preferred `after` order does not pull another source into this run. When
   the task is one source at a time, follow **Install and enable one source**
   and finish that run before the next source. Missing common-command support
   remains a blocker, not permission to invent source-specific orchestration.
5. **Work and verify.** Use separate worker and verifier duties. Adjust dispatch
   between invocations within supported limits as capacity changes. Changing a
   frozen contract or input requires new work; preserve the existing run. Inspect
   progress, contention, failures and pending events with bounded queries. Use
   [Change Journal](../change-journal/SKILL.md) for receipts/delivery recovery through
   the producer that owns the outbox, never direct edits to journal or run state.
6. **Close or hand off.** Finalize only after declared work is independently verified,
   source outcomes reconcile and required Journal deliveries are acknowledged. An
   unchanged repeat should select zero files and start no mastering work. Report a
   partial run honestly. Save the run ID, frozen evidence references, resource
   measurements, blocker and next action in the source runbook for the next agent.

For a monitoring request, set an explicit deadline and exit on completion,
blockage, cancellation or the deadline. At expiry retain resumable state and
report the next action. Scheduling a future invocation is separate deployment work.

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
