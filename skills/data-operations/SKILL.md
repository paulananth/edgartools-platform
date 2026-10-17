---
name: data-operations
description: Operates every domain and applies the DDL for MDM, RDM, Bookkeeping, Change Journal and silver on PostgreSQL, MySQL or SQL Server Express. Use when making those stores operational, applying a schema or an approved silver spec, operating daily loads, checking source readiness, managing a backlog, monitoring a run or maintaining its operational runbook.
---

# Data Operations

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
runtime readiness certificate. Recover retained progress before making a new run.

When deploying tested configuration to an environment, follow **Configuration
promotion** in RUNBOOK.md. Reuse the existing Rules approval procedure and exact
release evidence; distinguish an approved release from its active deployment.

## Apply store DDL

This skill applies DDL. Data-profiling writes a logical silver spec and does
not. MDM engineering writes the MDM migration files and does not apply a
profile's silver spec.

Apply these five schemas on the engine the environment names: PostgreSQL 16,
MySQL, or SQL Server Express. When that engine does not answer, start its
container from [Local testing](../data-platform/LOCAL-TESTING.md). The
container has no agent and no worktree owner. Do not use
`local-test-stores.py up` for it. Read each command's `--help` before the
first use. A missing subcommand, or a command that refuses the dialect, is a
runtime gap. Report it and leave that schema unapplied. Do not hand-write
`CREATE TABLE`.

The commands below exist for PostgreSQL 16. Each one refuses MySQL and SQL
Server Express. That refusal is the gap for those engines.

| Schema | Command | Owner connection |
|---|---|---|
| MDM | `edgar-warehouse mdm migrate --application-role <role>` | `MDM_DATABASE_URL` |
| RDM | `edgar-warehouse rdm init --runtime-role <role>`, then `rdm migrate` | `RDM_MIGRATION_DATABASE_URL` |
| Bookkeeping | `edgar-warehouse bookkeeping init --runtime-role <role>`, then `bookkeeping migrate` | `BOOKKEEPING_CLEAN_MIGRATION_DATABASE_URL` |
| Change Journal | `edgar-warehouse change-journal init --runtime-role <role>`, then `change-journal migrate` | `CHANGE_JOURNAL_MIGRATION_DATABASE_URL` |
| Silver | `edgar-warehouse silver init --runtime-role <role>`, then `silver migrate` | `SILVER_MIGRATION_DATABASE_URL` |

The runtime role exists, is not a superuser, and is not the migration login.
Done when each command reports the schema current. `edgar-warehouse doctor`
shows the stores that answer.

## Operationalize every domain

Do this after the five schemas are current, for every domain. A domain is one
source directory under `rules/sources` together with every entity kind that
source's merge policy names. Walk all of them. Company and Person are two
domains, not the list.

1. **Stores.** Confirm the five schemas in **Apply store DDL** are current on
   the named engine. A refusal from MySQL or SQL Server Express stays a gap.
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
   is the DDL for MySQL and for SQL Server Express. `silver register` today
   emits PostgreSQL only and refuses another dialect. That refusal is a
   runtime gap: report it and leave the table unregistered. Do not hand-write
   `CREATE TABLE`. A part with no approved spec, or a pipeline silver step
   with no worker, stays blocked and is reported. `silver land` is the manual
   write until that worker exists
   ([data-onboarding](../data-onboarding/SKILL.md), Two targets).

A domain is operational when its MDM source and merge policy are the active
proven versions, every code set it pins is published in RDM, and every approved
silver spec is a registered table. Report one line per domain: operational, or
the blocker. The recurring loop below then loads that domain's entities from a
finished delivery. This section does not download, does not invent a command,
and does not mark a blocked domain complete.

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
   leases. Run declared local prerequisites only through supported approved paths;
   a preferred source order is not a dependency. Missing common-command support
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
