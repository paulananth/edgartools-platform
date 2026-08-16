# Decide the Canonical Bronze-to-Silver-to-Snowflake Flow

Type: grilling
Status: resolved

## Question

Which persistent representations are required between immutable SEC Bronze and
Snowflake, and can the platform eliminate both Warehouse Gold Parquet and any
other duplicate derived datasets while retaining one canonical AWS Silver
publication, deterministic replay, fail-closed promotion, and recoverable
Snowflake ingestion?

The decision must distinguish the durable Silver state stored in the Warehouse
bucket from the `warehouse/gold/**` derivatives and the Snowflake-export
transport package. It must state whether Snowflake consumes Silver directly or
through a transient transport representation, which system owns Gold, and what
recovery evidence replaces any removed intermediate copy.

## Comments

### Repository findings (2026-08-01)

- The Warehouse bucket is required today because it is the physical home of
  canonical Silver (`warehouse/silver/sec/silver.duckdb` and shards). Bronze is
  immutable source evidence, not the normalized/current-state database.
- A Gold refresh builds each table once as an Arrow table, then independently
  serializes it to `warehouse/gold/**` and to the Snowflake-export bucket. This
  is a real duplicate derived representation and duplicate Parquet
  serialization.
- No runtime consumer reads `warehouse/gold/**` back. Its only code-visible
  downstream value is the `gold_manifest` hash/path/delta record stored inside
  Silver; the Snowflake-export write can return and record equivalent checksum,
  size, row-count, and lineage evidence.
- Snowflake cannot natively consume the current Silver DuckDB file. Removing
  both derived S3 representations therefore requires replacing native S3 pull
  with direct authenticated writes from ECS or changing the Silver format and
  Snowflake ingestion architecture.

## Answer

Retain exactly two durable AWS data layers: immutable SEC Bronze and canonical
Silver in the Warehouse bucket. Remove `warehouse/gold/**`, eliminate the
Snowflake-export bucket, and make Snowflake the sole owner of Gold data.

Gold publication must use an authenticated direct Snowflake writer from the
warehouse ECS task. The writer stages each table in Snowflake-managed internal
storage, publishes a complete run manifest only after every table is present,
and invokes the run-scoped loader synchronously. A failed or incomplete run
must remain unpromoted. Checksums, row counts, source run identity, and load
status replace evidence previously split across Warehouse Gold and the export
bucket. Bronze plus canonical Silver remain the deterministic replay sources.

The production export bucket must not be destroyed until the direct publisher
has passed end-to-end acceptance on an immutable deployed image. Bucket
deletion is the final cutover action, not a prerequisite for validating the
replacement path.

### 2026-08-16 outcome (recovered from an orphaned worktree, never committed)

This decision and its implementation attempt (see
[Implement Direct Run-Scoped Snowflake Publication](08-implement-direct-run-scoped-snowflake-publication.md))
were made inside an `ops-cost-control` session on 2026-08-01 but only ever
existed as uncommitted working-tree state in a since-abandoned worktree — never
committed, never pushed with commits, never opened as a PR. Two days later
(2026-08-13/14) a separate effort, `silver-snowflake-migration`, shipped a
different design instead: native S3 pull and the Snowflake-export bucket were
kept, with an incremental landing zone added alongside them. That is the
architecture live in production today; this ticket's "Answer" was never
carried out.

Recovered and cost-compared on 2026-08-16 (see
[08](08-implement-direct-run-scoped-snowflake-publication.md)'s outcome note
for the analysis) before closing this thread out. Filed as **out of scope**
for this map — see `map.md`'s Out of scope section — because eliminating
`warehouse/gold/**`/the export bucket is a data-architecture redesign beyond
this map's own Destination (CloudWatch/ECR cost), not because the decision
itself was wrong on its own terms.
