# Hosted PostgreSQL mirroring

Use the installed `snowflake-postgres` skill first for Snowflake-hosted
PostgreSQL. For managed mirroring, follow its `mirror` sub-skill and
`mirror/references/type-mapping.md`; set the target table format explicitly
from the approved architecture. The selected platform design uses one
Snowflake-managed Iceberg mirror database. Do not substitute pg_lake, Openflow,
exports or hybrid tables for that managed mirror.

For one target database containing Iceberg tables across several source schemas,
follow [Single-database Iceberg qualification](SINGLE-DATABASE-ICEBERG.md)
from an empty isolated source. It requires one PostgreSQL source database,
explicit approved tables and `target_table_type => 'ICEBERG'`; it does not
consolidate existing production stores or create billable resources implicitly.

The target flow is PostgreSQL MDM, RDM and Silver final outputs → the read-only
mirror database (`mirror.database` in `rules/snowflake.yaml`). Approved consumers can read those
tables directly; dbt is not required for replication or direct consumption.
When requirements call for Gold joins, calculations, aggregates or reporting
models, dbt reads approved mirror sources and writes to a separately approved
writable destination outside the managed mirror database: `gold` in
`rules/snowflake.yaml`. A new destination needs its own approval; neither an
example nor an existing operational object approves one. Follow [Gold requirements](../data-modeling/GOLD.md)
before building it. Treat source consolidation, managed mirror qualification,
consumer access and Gold model qualification as distinct gates. The hosted
Postgres ingress rule needs an approved writable control location independent
of whether Gold is built.

## Readiness before changes

A read-only identity cannot read the instance: `SHOW POSTGRES INSTANCES` and `DESCRIBE POSTGRES INSTANCE` list only an instance on which the role holds
OPERATE or OWNERSHIP, and OPERATE can also stop, resize and reset it. So the pre-flight does not widen the audit role: the instance's compute
family, version, state, storage and high-availability setting are read once by the account owner (names and numbers only, never the access
details) and written into the create plan, then read again when the plan is approved. The Gold destination's schemas, objects and network
rule are read by the audit role, which holds USAGE on the database and its schemas and REFERENCES on its tables (metadata, no rows).
The account's rates are read by the same role from `SNOWFLAKE.ORGANIZATION_USAGE.RATE_SHEET_DAILY` (it holds the `ORGANIZATION_BILLING_VIEWER` database role, which also shows invoices and
contract items: billing data, read-only). A service type appears in the sheet only once the account has used it, so a mirror's own rates are confirmed after its first day, and a plan states
which rates were read and which were assumed.

Use `aws-snowflake-operations` before Snowflake commands. Inspect the selected
account, role and instance live. Keep credentials, database addresses and
DESCRIBE `access_roles` out of output. Report counts and metadata only.

- Managed mirroring requires a supported AWS or Azure instance in the same
  account and region. Supported compute families are `STANDARD_*` and
  `HIGHMEM_*`; `BURST_*` is burstable and blocks mirror pre-flight.
- A resize is a separate billable change. Present the proposed family,
  current credit rates and failover impact for explicit approval. Verify the
  resulting family and READY state; an accepted ALTER is not completion.
  Keep the approved change in a committed script or infrastructure definition.
  The reusable SQL template lives with this skill:
  [resize_instance.sql](scripts/resize_instance.sql).
  Execute it through Snow CLI with an explicit connection and role,
  `--enable-templating JINJA`, and reviewed literal variables. Before rendering,
  require `instance_name` to match `^[A-Za-z_][A-Za-z0-9_]*$` and choose
  `compute_family` from the installed skill's documented supported family list.
  Jinja substitutes text; never pass data-derived values. The template applies
  failover as soon as the replacement is ready.
- For read-only readiness, use `pg_connect.py --ensure-ready` with
  `--no-auto-resume`. A suspended instance needs approval to resume compute.
  Use `connect_timeout=10` and command timeouts of at least 60 seconds.
- Verify the source database and every selected schema, not a guessed default.
  A layer stored in its own database is not necessarily a schema of a shared
  database. Verify each target Snowflake database is absent.
- Enumerate every source relation, persistence and primary key. Report
  unsupported relations, missing primary keys (insert-only replication),
  reserved mirror suffixes and case-insensitive identifier collisions.
  Complete the type scan, including domain, composite and array base types.
  Stop on a blocked type or any unverified check.

Preserve the platform's exact-number contract: unbounded or oversized numeric
columns that would mirror as DOUBLE require an explicit resolution before
creation. Report JSON-to-string and other fallback mappings from the owning
skill. Do not silently change source types to get past pre-flight.

## Creation and verification

### Resolve approved exposure tags

Read the configured exposure-tag identity and table assignments from the
approved requirements/mapping version described in
[Final exposable tables](FINAL-TABLES.md). Select only tables explicitly carrying
that approved tag in configuration. An absent, pending, declined or stale
assignment selects nothing; a data-class or certification tag is insufficient.
Resolve each selected asset to its exact source database/schema/table and
check its final-output role and current/history scope. Unknown identities,
missing physical tables or an unsupported selector block creation; an empty
selection never falls back to the schema.

OpenMetadata displays these assignments, but its manual tags cannot add tables
to the selection. Report its tag-projection/readback separately from physical
mirror readiness. List both included and excluded tables with their requirement
and mapping references in the create plan. Keep reusable tag-resolution helpers
with the owning skill or application package, never under `infra/`.

Apply [Final exposable tables](FINAL-TABLES.md) first. Use explicit
`postgres_tables` with `postgres_schemas => NULL`; only configured final master
and silver outputs are in scope. Schema-wide mirroring cannot enforce this
boundary. Verify the exact physical table list, not only table counts.

Use the same tag-resolved list for additions and verification. Adding a tag
does not itself call `ALTER_MIRROR`; follow the normal add-table workflow.
Removing a tag makes the table ineligible for further configured exposure,
but does not erase an existing mirror or its data. Report the discrepancy and
obtain the existing removal approval before `remove_tables` or any drop.

After verified pre-flight, follow the mirror sub-skill's grant sequence and
present each mirror, source database/schema, target database, refresh interval,
serverless or warehouse selection, exclusions, insert-only tables and costs.
Resize approval does not approve mirror creation. Wait for explicit approval
before `SNOWFLAKE.POSTGRES.CREATE_MIRROR`; it creates billable infrastructure.

Two permissions a mirror needs beyond the sub-skill's grant sequence:
- The role that calls `CREATE_MIRROR` must own the Postgres instance ("does not own the requested postgres instance"):
  the mirror operator does (aws-snowflake-operations, "Access identities"); the administrator never creates a mirror.
- Snowflake's system login `snowflake_system` must hold CONNECT on each mirrored database ("permission denied for
  database"): the stores revoke it from PUBLIC, and `infra/scripts/harden-hosted-roles.py` grants it.

**The managed mirror record is the system of record.** `sources/managed-mirror.yaml` lists the tables, mirror name, source database,
refresh interval, table format and approval. The target database comes from `rules/snowflake.yaml`; the mirror scope is checked
against `destination/authorised_data_sharing.yaml`.
Gold's dbt source file may read only listed tables (`mirror_sql.py check --reads <sources file>`), and the record may list only
tables the exposure list approves. The exposure list is the upper bound, not the mirror list: an unexposed table is refused,
and an exposed table nothing in Snowflake reads stays out. The catalog publishes approved exposure from the stores, not the mirror.
`verified` is current read-back state. Keep it false while the target is absent or after a source-store reset; set it true only
after the current mirror's readback passes. A prior successful readback does not qualify an absent or reset target.
Changing the table list changes the mirror: record the operator's words, then use `scripts/exposure/mirror_sql.py alter`.
Working tables (the merge stage, reviews, decisions, lookups, progress) are never mirrored. Each mirrored table is a full copy
kept current at the refresh interval, so its size is a cost: state every table's size in the plan. A table removal needs approval.

**Plan the mirrors from the read list, never table by table.** Group the read tables by the database that holds them:
each database is one mirror, and each schema keeps its name in the target. Read the instance's publication limit and the
publications already held; when the databases to mirror outnumber the free publications, the answer is the store layout
(every exposed store in the data database, [Connection URLs](CONNECTIONS.md)), not a support request or a dropped mirror. The
data database gives one mirror, the `mirror.database` of `rules/snowflake.yaml`, with one schema per source schema; a plan with more than one target
database for the exposed stores is a defect. Only the data database is mirrored, never the control database (Bookkeeping, Change Journal) nor the config database (Rules):
`scripts/exposure/mirror_sql.py exists` reads back whether the target database exists (`SHOW DATABASES LIKE`, no administrator needed: it is absent before a create and after a retire). `scripts/exposure/mirror_sql.py plan --publication-limit <n> --publications-held <n>` writes the plan (tables per schema, the one publication) or refuses a record
that names another database, a table whose layer is not on `DATA_URL`, or no free publication.

An instance carries at most two mirrors: each mirror needs one CDC publication and `snowflake_cdc.max_publications`
is 2, which `POSTGRES_SETTINGS` does not accept ("Unrecognized Postgres setting"). A third mirror needs Snowflake support
to raise it; until then, choose the two the readers need first. Read the limit and the publications held before a create
(`show snowflake_cdc.max_publications`, `pg_publication` in each mirrored database).

**Database names are configuration** (`rules/snowflake.yaml`, one block per part); no script, profile or grant repeats one.

**A live target is owned by the Snowflake application, not by the owner role; an orphan can be moved and dropped.** Proved on a probe mirror: while a mirror
replicates (active or suspended) `GRANT OWNERSHIP` on its target is refused ("cannot be transferred while the mirror is active"), `CREATE_MIRROR` refuses a
database that already exists (even one the mirror operator owns, so ownership cannot be arranged in advance), and `ALTER DATABASE ... RENAME` and
`DROP DATABASE` are refused for the administrator and for the mirror operator ("must have OWNERSHIP"). A target left by
`DROP_MIRROR(<mirror>, FALSE)` has no mirror, and the administrator can then `GRANT OWNERSHIP ON DATABASE <name> TO ROLE <owner role>` (without `COPY CURRENT GRANTS`, which
is refused for an application-owned object; the mirror operator alone gets "Insufficient privileges") and the owner role drops it: no support request. `scripts/exposure/mirror_sql.py release` writes both steps for a mirror whose target the owner role should own: the data stays, but nothing refreshes it. So:
- rename by recreating, with `scripts/exposure/mirror_sql.py` (it writes the `CREATE_MIRROR`, `ALTER_MIRROR`, `LIST_MIRRORED_TABLES` and `DROP_MIRROR`
  text from `sources/managed-mirror.yaml`, `destination/authorised_data_sharing.yaml` and `rules/snowflake.yaml`, so no call is typed by hand): `CREATE_MIRROR` (the skill's SETUP) with the new target name and a new mirror name, as the mirror operator, while
  the old mirror still replicates (an instance holds two); when every table reads `REPLICATING` with equal counts, move the readers and
  the configuration, then `DROP_MIRROR(<old mirror>, TRUE)` so its target goes with it;
- always drop a mirror with the second argument `TRUE`, never `FALSE`.

A mirror's target schema takes the source schema's name in upper case (`rdm` gives `RDM`, `mdm` gives `MDM`; nothing is exposed from `public`, so a table there is a defect the audit's SCH control and `mirror_sql.py plan` refuse), so
the readers of a mirror name the target database and that schema.

On permission or extension errors, stop without retrying and direct the
operator to refresh the instance in Snowsight (Postgres → Manage), as required
by the mirror workflow. Do not improvise extension installation.

Verify per-table state with `LIST_MIRRORED_TABLES`: SNAPSHOTTING then
REPLICATING. Mirror listings do not supply a mirror-level state. Allow initial
metadata to populate before treating an empty table list as failure. Compare
source and target row counts, noting concurrent writes and refresh lag; counts
alone do not prove value equality. Report every excluded or insert-only table.

Base tables reflect the last consistent apply. `$LIVE` offers lower latency
without transaction consistency and can cost more. `$CHANGES` retains seven
days. Require explicit approval for table removal, restart (full re-snapshot
and loss of change-feed history), or mirror drop. Grant consumers read access
only when requested; the mirror owns target writes.

## At init: mirror only what Gold reads

The mirror is created at init, and again after a reset, for the tables `sources/managed-mirror.yaml` lists and no others
(Gold reads only those; each must be on `destination/authorised_data_sharing.yaml`, which [Final exposable tables](FINAL-TABLES.md) owns). A read table must
exist before a mirror can take it, and init's silver step makes every one, empty; the mirror's change capture then carries each load's writes, so no
step waits for a load. The readiness gate's `MIRRORED` check keeps a load from starting before the mirror is exactly its record. The order, after init's silver step:

1. Resolve the exposure list against the initialized stores, read-only, with the exposure tooling ([its README](scripts/exposure/README.md):
   `generate`, then `check`). It refuses a listed table or column the stores lack.
2. Write the Gold project from its configuration ([data-modeling GOLD.md](../data-modeling/GOLD.md)), then check that it reads only the record
   (`mirror_sql.py check --reads <dbt folder>/models/sources.yml`) and write the create text from the record (`mirror_sql.py create --instance <instance>`).
3. Follow [Readiness before changes](#readiness-before-changes) and [Creation and verification](#creation-and-verification) on exactly
   those tables: explicit `postgres_tables`, `postgres_schemas => NULL`, `target_table_type => 'ICEBERG'`
   ([the single-database qualification](SINGLE-DATABASE-ICEBERG.md) pins the rest).

**One mirror, of the data database.** Every exposed store is a schema of the one data database, so the listed tables get one mirror with one
target database (`mirror.database`) and the schemas `MDM`, `RDM` and `SILVER`. Never one mirror per store, never one reading the control or the config database.
The create plan names the one source database, its tables per schema, its target and its refresh interval, and is approved before it runs
(`mirror_sql.py plan`). RDM lists the published-only table, never the tables that hold drafts: a mirror carries tables, not views.

**Done is read back, not assumed:** list the mirror (`mirror_sql.py verify`; its first call can return no rows while metadata fills, and each table's
`state` stays SNAPSHOTTING until its snapshot ends, about 10 minutes for 20 million rows), save the rows (`source_schema_name`, `source_table_name`,
`state`) as JSON, and run `mirror_sql.py readback --listing <file>`. It fails naming what is missing, unexpected or still snapshotting, and passes only when the mirror is exactly
the record with every table REPLICATING; then set `verified: true` in `sources/managed-mirror.yaml`. Read the snapshot cost from metering history
(`SERVERLESS_TASK` lines lag by hours) against the 5-credit bound.

For a hosted table reset, suspend the mirror as the mirror operator
(`mirror_sql.py suspend | mirror_run.py`; `mirror_run.py` runs one statement with the operator's key pair and prints its
rows as JSON), then verify `SUSPENDED` with `mirror_sql.py status | mirror_run.py`. After the reset,
`mirror_sql.py resume | mirror_run.py`. Suspension pauses Snowflake apply. A PostgreSQL WAL sender can remain
connected, so check source sessions and logical slot activity separately before
running the table reset (`reset-hosted-tables.py --wait-minutes` waits for them and names what stays). Read `pg_stat_activity` by backend type and transaction
state, and `pg_replication_slots` by slot type and active state for the source
database. An active logical slot means the source connection still needs to
drain even when Snowflake reports `SUSPENDED`. Use the managed lifecycle for
replication and extension workers.
If the reset requires tearing down the mirror or taking a new snapshot, use the
separate approval for that lifecycle action.
