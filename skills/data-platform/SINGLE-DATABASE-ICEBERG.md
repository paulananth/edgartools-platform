# Qualify a single Iceberg mirror database

Use this procedure when the requested mirror destination is one database with
separate final master, reference and silver schemas. Start from an empty,
isolated test source; production migration is a separate decision. Follow the
installed `snowflake-postgres` mirror sub-skill and
[Final exposable tables](FINAL-TABLES.md), including the integrated
requirements-and-mapping approval of the exact table list.

## What must be proved first

Managed mirroring selects one PostgreSQL source database and creates a new
Snowflake target database. `target_table_type => 'ICEBERG'` changes the target
table format, not the database boundary. Three independent source databases
cannot feed three managed mirrors into the same existing target. One source
database can supply selected tables from several schemas to one mirror.

Verify current support against the official
[create guide](https://docs.snowflake.com/en/user-guide/snowflake-postgres/postgres-data-mirroring-create)
and [procedure reference](https://docs.snowflake.com/en/user-guide/snowflake-postgres/postgres-data-mirroring-reference).
Capture the service version/signature and actual result of the installed
procedure during qualification. Documentation support is not hosted proof.

## 0. Freeze the test and its expected answers

Before writes, record an execution checklist with the selected environment,
unique source database, mirror and target names, configured tag identity,
approved synthetic table list, expected rows/types, interval, duty roles,
deadline and cleanup scope. Keep addresses and credentials private. Use a new
qualification target name each time: mirror target names cannot be reused.
Preserve the requested production name for production.

Use an isolated test instance or an explicitly approved test database on an
existing instance. A new instance, mirror, serverless apply task or warehouse
has its own cost/approval boundary. Estimate 60–90 minutes for a hosted proof
with 30-minute observation intervals; use a 90-minute deadline and stop on any
failed acceptance check. An empty initial table listing may need another check;
do not mistake asynchronous registration for success or immediately retry create.

Reuse Snow CLI for Snowflake SQL and `psql` or the owning skill's `pg_common`
driver for PostgreSQL. Include `connect_timeout=10`, command timeouts of at
least 60 seconds and bounded statement timeouts. Reuse the existing dbt CLI
for the Gold check. These steps do not require a new orchestration script.
If an existing client cannot express a required check, reproduce that gap
before adding a source-neutral helper under the owning skill's `scripts/`.
Do not add generic workflow helpers under `infra/`.

## 1. Establish a clean source boundary

Verify READY, supported Standard/High Memory compute, same-account/region
AWS/Azure placement and a working restricted test connection. Use
`--no-auto-resume` for read-only readiness. Check mirror privileges and instance
USAGE for the Snowflake application without rotating credentials or showing
DESCRIBE access-role values. Stop on an unverifiable check.

In the one empty test database, create the three configured layer schemas and
one logged ordinary final-output table per schema. Use the same fixture shape
for all layers through a configured list, not separate provider/kind scripts.
The fixture has a BIGINT primary key and NUMERIC(38,9) measure. Seed exactly
three invented rows per table, including an integer above the exact binary
floating-point range and a decimal with many digits. Include untagged and
internal tables as exclusion controls. Do not copy production records.

Verify `current_database()` is identical for all three layer connections,
schema/table identity, logged persistence, primary keys, exact declared types
and initial contents. Scan every proposed column using the installed type
reference, including nested/domain types. Unsupported or lossy numeric mappings
block the proof rather than silently converting numbers to floating point.

## 2. Prove the selection before creating a mirror

In the requirements/mapping review, show the three final tables, their fields,
grain, keys, time scope and exact expected selection. Record the approved
configuration/tag assignments. Resolve them to three physical `schema.table`
names in the single source database. Assert equality with the expected set.

Exercise absent, pending, declined and stale assignments, an empty selection,
an unresolved physical name and an attempted cross-database selection. Each
must select nothing or block planning; none may fall back to schema scope.
An internal table must remain excluded even if a catalog-only tag is added.
Changes to requirements or mappings reopen only affected selection entries.

If the configuration parser or tag resolver is missing, record that as a failed
gate. A separately approved three-table Iceberg capability experiment may still
use a manually reviewed explicit list, but label it **capability proof only**:
it does not qualify automated tag selection or either consumer's activation.

## 3. Create one Iceberg mirror after approval

Confirm the unique target database is absent; do not pre-create it. Present the
exact resources, table list, format, interval, serverless/warehouse choice,
cost boundary, deadline and cleanup plan for explicit approval. A skill edit,
source fixture or requirements approval does not approve this billable create.

Use one `SNOWFLAKE.POSTGRES.CREATE_MIRROR` call with one source database,
`postgres_tables` set to the resolved list, `postgres_schemas => NULL`,
`target_table_type => 'ICEBERG'`, `warehouse => NULL` and
`external_volume => NULL` for Snowflake-managed storage. Pin the chosen
refresh interval; do not fall back to native Snowflake tables if Iceberg is
rejected. On permission/extension errors, stop and follow the installed
skill's grant/instance-refresh diagnosis; never install extensions manually.

## 4. Verify the initial snapshot, not only counts

Use `LIST_MIRRORED_TABLES` to verify exactly three selected source tables reach
REPLICATING, with exclusions absent. Companion/system objects are expected;
do not count them as extra business tables. Confirm source-to-target schema,
table and column mapping and verify every selected target is an actual
Iceberg table using the service's object metadata (`SHOW ICEBERG TABLES`),
not an ordinary table or a view. Unquoted target names fold to uppercase.
The companions are one `<TABLE>$CHANGES` Iceberg table per mirrored table, on
the mirror's own catalog integration, and one table under `SNOWFLAKE_CDC_LOGS`;
a base table shows the Snowflake catalog and the Snowflake-managed volume.
`LIST_MIRRORED_TABLES` names each row by `SOURCE_SCHEMA_NAME` and
`SOURCE_TABLE_NAME`, with `STATE`, `SNAPSHOT_STATE` and `LAST_SNAPSHOT_ERROR`.
Check the target types too: `bigint` arrives as `NUMBER(19,0)` and
`numeric(38,9)` as `NUMBER(38,9)`.

Read every synthetic row, key and exact decimal back from each base target
table and compare with the independently written expected set. Turn each decimal
into text in Snowflake (`TO_VARCHAR(<column>, 'TM9')`), since a client that
reads it as a float loses the digits the check is for. Counts must
also equal three per table. Compare JSON/string fallback representations only
when the approved requirement expects that mapping. Base tables are the
consistent proof target; `$LIVE` is not a substitute for transactional checks.

## 5. Exercise change capture from the beginning

Apply the same configured mutation sequence to each layer table in the source:
insert one new key, change one existing value and delete a different key.
Use one committed cross-schema transaction to test preservation of its final
result, then a separate transaction that rolls back and must never appear.
The committed mutation set deliberately leaves the row count unchanged, so
the verifier must compare keys and values as well as counts. Verify there are
no duplicates and deleted keys are absent. Repeat the read with no new writes;
the expected contents must remain identical.

Record each source commit marker and the expected final set. Check the target
after its apply interval at the normal observation point. For an atomicity
claim, read all three base tables in one Snowflake statement and accept only
the complete before or complete after result; sequential queries spanning an
apply can give misleading evidence. A final-state match alone does not prove
that no transient partial state was ever observable.

## 6. Prove read-only consumption and Gold separately

Use a test consumer with USAGE and SELECT only on the approved targets, granted
table by table so the `$CHANGES` companions stay out of its reach.
Verify reads succeed and an INSERT/UPDATE attempt is denied under that
consumer role, inside the isolated fixture scope. Do not test as ACCOUNTADMIN
or infer read-only access because a table's name contains mirror.

Direct mirror consumption does not require dbt or a Gold build. When the
qualification includes a required Gold transformation, declare the three
Iceberg targets as dbt sources. Build the smallest synthetic
Gold model that joins their fixture keys and computes an exact numeric result
in a separately approved test Gold target; run its key, uniqueness, non-null
and exact-result checks. Gold gets no write grant on mirror tables. A missing
dbt project/adapter or failed model is a separate unqualified stage, not a
reason to call mirror replication failed or Gold ready.

Require the same resolved table set for AutoOntology source grants/inventory
and the OpenMetadata exposure-tag projection. Verify exact native readback,
including exclusion of internal controls. Keep this gate pending when the
selectors or publisher cannot enforce it; a manually successful Iceberg
experiment does not satisfy it. Do not start external inference for this test
without the relevant authorization.

## 7. Preserve evidence, then perform approved cleanup

Report separately: documented capability; source/selection checks; hosted
Iceberg snapshot; committed/rolled-back changes; exact-number checks;
consumer access; dbt Gold; catalog/AutoOntology selection; and production
readiness. Mark every stage passed, failed, blocked or not run, with counts
and actual local ET times. Keep secrets and record values private; only
invented fixture values may appear in public evidence.

On failure, retain pinned configuration and evidence before cleanup. Cleanup
requires approval naming the exact test mirror, target database, source
database and any test instance/Gold objects. Pass the target-database
flag explicitly, as the second positional argument: `DROP_MIRROR('<mirror>',
TRUE)`. The named form `drop_target_database => TRUE` after a positional
mirror name is refused. Never rely on a destructive default. Do not
restart/re-snapshot just to get a green result. A mirror left running after a deadline keeps
incurring cost; arrange authorized scoped cleanup or report the remaining
billable resources. Preserve production and other agents' databases/volumes.

Passing the synthetic proof establishes the one-source/one-target Iceberg
capability only. Before production consolidation, separately qualify callers,
schema isolation, restricted roles, migrations, stored history, recovery and
rollback for the real application stores. Do not consolidate them as a side
effect of this test or replace the required Iceberg target with three databases.

## Examples

The requested production target is `DB_EDGARTOOLS_MIRROR` with `MDM`, `RDM`
and `SILVER` schemas. Consumers may read approved mirror tables directly.
When Gold transformations are required, dbt reads the mirror and writes to a
separately approved writable destination; no Gold database/schema name is
approved by this example. A qualification uses a unique disposable target such as
`DB_EDGARTOOLS_MIRROR_Q_<unique>` instead of consuming that production name.
One source test database contains `mdm.final_data`, `rdm.final_data` and
`silver.final_data`; only these three tables are selected. The three initial
keys can be 1, 2 and 9007199254740993; measures can be 1.250000000,
2.750000000 and 12345678901234567890.123456789. Write decimal expectations
as exact strings/decimals, never through floating point. Insert key 4, update
key 2 and delete key 1: three rows remain, but a counts-only check misses bugs.

The following SQL is a reusable synthetic fixture for an empty isolated source
database, not a production initialization. Use the existing SQL client; execute
the seed first, then take initial expected-row readbacks. Execute the mutation
only at the CDC step after the approved mirror's initial snapshot completes.
Each block uses one schema list for all layers. For a local fixture-only test,
run them in order on disposable PostgreSQL 16 and verify both readbacks; that
does not qualify Snowflake or Iceberg. The SQL is kept here rather than adding
another script or command to the platform.

Seed:

```sql
DO $fixture$
DECLARE
  layer text;
BEGIN
  FOREACH layer IN ARRAY ARRAY['mdm', 'rdm', 'silver'] LOOP
    EXECUTE format('CREATE SCHEMA %I', layer);
    EXECUTE format('CREATE TABLE %I.final_data '
      '(id bigint PRIMARY KEY, measure numeric(38,9) NOT NULL)', layer);
    EXECUTE format('CREATE TABLE %I.internal_data (id bigint PRIMARY KEY)', layer);
    EXECUTE format('CREATE TABLE %I.untagged_data (id bigint PRIMARY KEY)', layer);
    EXECUTE format('INSERT INTO %I.final_data VALUES '
      '(1, 1.250000000), (2, 2.750000000), '
      '(9007199254740993, 12345678901234567890.123456789)', layer);
  END LOOP;
END
$fixture$;
```

Committed cross-schema mutation:

```sql
DO $changes$
DECLARE
  layer text;
BEGIN
  FOREACH layer IN ARRAY ARRAY['mdm', 'rdm', 'silver'] LOOP
    EXECUTE format('INSERT INTO %I.final_data VALUES (4, 4.250000000)', layer);
    EXECUTE format('UPDATE %I.final_data SET measure=5.500000000 WHERE id=2', layer);
    EXECUTE format('DELETE FROM %I.final_data WHERE id=1', layer);
  END LOOP;
END
$changes$;
```

Rolled-back cross-schema mutation (must never appear in target readback):

```sql
BEGIN;
DO $rollback$
DECLARE
  layer text;
BEGIN
  FOREACH layer IN ARRAY ARRAY['mdm', 'rdm', 'silver'] LOOP
    EXECUTE format('INSERT INTO %I.final_data VALUES (99, 99.000000000)', layer);
  END LOOP;
END
$rollback$;
ROLLBACK;
```

After the committed changes, each final table must contain exactly keys 2, 4
and 9007199254740993 with measures 5.500000000, 4.250000000 and
12345678901234567890.123456789 respectively. Key 1 is deleted and key 99 must
be absent. Check the same expected rows on PostgreSQL and Snowflake; a row
count of three alone is insufficient. Keep the initial readbacks too.
