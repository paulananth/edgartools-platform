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
`DB_EDGARTOOLS_MIRROR` Iceberg database. Approved consumers can read those
tables directly; dbt is not required for replication or direct consumption.
When requirements call for Gold joins, calculations, aggregates or reporting
models, dbt reads approved mirror sources and writes to a separately approved
writable destination outside the managed mirror database. Gold database and
schema names remain undecided; neither an example nor an existing operational
object approves a target. Follow [Gold requirements](../data-modeling/GOLD.md)
before building it. Treat source consolidation, managed mirror qualification,
consumer access and Gold model qualification as distinct gates. The hosted
Postgres ingress rule needs an approved writable control location independent
of whether Gold is built.

## Readiness before changes

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
