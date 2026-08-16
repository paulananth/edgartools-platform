# 01 — DuckDB httpfs partial read/write feasibility against the canonical silver.duckdb

Type: research
Status: resolved
Blocked by: none
Blocks: everything else on this map (the write-back mechanism, protected-merge
safety, and the Option A/C fallback decision are all downstream of this
answer)

## Question

`seed-universe` currently must fully download (`read_bytes`, the whole S3
object into memory) and locally open the canonical `silver.duckdb`
(1,517MB as of 2026-08-08 and growing) before it can run two operations
against exactly one table, `sec_company_sync_state`:

1. **Read**: `SilverDatabase.get_active_ciks()` — effectively
   `SELECT cik FROM sec_company_sync_state WHERE tracking_status = 'active'`.
2. **Write**: `SilverDatabase.upsert_company_sync_state(...)` (called via
   `_seed_silver_tracking_status`) — an `INSERT ... ON CONFLICT (cik) DO
   UPDATE ...` upsert for newly-discovered CIKs, tagging them
   `bootstrap_pending`.

This ticket investigates whether DuckDB's `httpfs` extension (or any other
DuckDB-native mechanism) can do BOTH of these against the canonical
`silver.duckdb` object sitting in S3 (`s3://edgartools-prod-warehouse-690839588395/warehouse/silver/sec/silver.duckdb`)
**without downloading the full file first**, specifically:

- Does DuckDB's `httpfs`/`ATTACH ... (READ_ONLY)` support attaching a
  *remote* `.duckdb` database file over S3 and querying a single named
  table, reading only the pages/row-groups that table actually occupies
  (not the whole file)? Cite DuckDB's actual documented behavior/version
  requirements, not assumption — this repo already pins a DuckDB version
  (check `uv.lock`/`pyproject.toml`), confirm the attach-remote-database
  feature is present at that version.
- Does `httpfs` (or any DuckDB extension) support *writing* to a table
  inside a remote-attached `.duckdb` file directly, or is remote attach
  strictly read-only in DuckDB's actual implementation? If write-through
  isn't supported, what does a full round-trip cost look like if the
  write path instead downloads/opens/merges/re-uploads **only a byte range
  or a much smaller derived copy** rather than the current full-file
  `read_bytes`/`write_bytes` pair — is there a DuckDB-native way to
  export/attach *just one table's* pages into a small standalone local file
  cheaply, without materializing the other ~30 tables?
- What are the actual latency/cost characteristics of a remote read against
  a 1.5GB S3 object via `httpfs` for a single small table lookup (row-group
  pruning behavior, number of S3 GET/range requests) — is this genuinely
  cheap, or does DuckDB's file-format layout mean a "targeted" query still
  requires reading a large fraction of the file's metadata/catalog
  structures regardless of which table is queried?
- Are there known caveats specific to concurrent access (another process
  editing the same S3 object mid-read) or IAM/credential requirements
  (`httpfs` needs its own S3 credential configuration, distinct from this
  repo's existing `boto3`/`fsspec` access pattern used everywhere else) that
  would affect adopting this in `edgar_warehouse/silver_store.py`/
  `warehouse_orchestrator.py`?

Report a clear, cited verdict: **feasible for read**, **feasible for
read+write**, or **not feasible as originally scoped** — and if partially
feasible, exactly which operations are safe to do this way and which still
need the existing full-hydrate path.

## Answer (2026-08-09, primary-source research: DuckDB official docs, `duckdb-web` and `duckdb` GitHub repos, this repo's lockfile)

### Pinned version

`uv.lock` pins `duckdb==1.5.2` (`pyproject.toml`'s constraint is only
`duckdb>=1.0.0`). Every capability cited below is checked against the
`docs/current` tree of `duckdb/duckdb-web` (the live docs, which track the
current release line) and cross-checked for version-gating. None of the
findings are gated behind a version newer than 1.5.2:

- Remote `ATTACH` over HTTPS/S3 has existed since **DuckDB 0.7.0** (Feb
  2023) — see the `0.7.0` release notes and
  `github.com/duckdb/duckdb/discussions/7781` (a live bug report against it
  filed the same era). Far older than the 1.0+ floor this repo already
  requires.
- `internals/storage.md` (`duckdb-web`, `docs/current/internals/storage.md`):
  "By default, DuckDB versions v1.0 to v1.5 create a DuckDB database file
  with version 64, corresponding to v1.0.0." — the on-disk format
  `silver.duckdb` is written in and the format the pinned client reads are
  the same storage version across the entire 1.0–1.5 line, so there is no
  format-compatibility gap to worry about.
- `s3_version_id_pinning` (cited below, the concurrency mitigation) and the
  `credential_chain` provider (cited below) are both present in the
  `docs/current` tree with no "added in X.Y" callout, i.e. long-standing,
  not new-in-1.5.x features.

No capability gap exists at 1.5.2 that would require an upgrade.

### 1. Read: targeted single-table read without downloading the whole file — FEASIBLE, confirmed by both docs and source

**Docs (behavior):** `ATTACH 's3://bucket/file.duckdb' AS db (READ_ONLY); SELECT ... FROM db.table_name;`
is the documented pattern
(`docs/current/guides/network_cloud_storage/duckdb_over_https_or_s3.md`,
`docs/current/sql/statements/attach.md`). Nothing in the documented syntax
requires downloading the object first — it is presented as a live query
target, the same way `read_parquet('s3://...')` is.

**Source (mechanism, since the docs don't spell out the byte-level
behavior for `.duckdb` files the way they do for Parquet — see the
"latency/cost" section below for that gap): `duckdb/duckdb`'s
`src/storage/single_file_block_manager.cpp` confirms this is a real
partial read, not "download then open locally":**

- `SingleFileBlockManager::LoadExistingDatabase` (`single_file_block_manager.cpp:625`)
  reads exactly three fixed-size header regions on attach — the main
  header at offset 0, and two rotating database headers at
  `Storage::FILE_HEADER_SIZE` and `Storage::FILE_HEADER_SIZE * 2` — via
  `ReadAndChecksum`, not a full-file read.
- Every subsequent block read goes through
  `SingleFileBlockManager::ReadBlock`/`Read` (`single_file_block_manager.cpp:1167-1187`),
  which computes a byte offset with `GetBlockLocation(block_id)` (`BLOCK_START
  + block_id * block_alloc_size`) and reads only that block — i.e. table
  data (and the catalog, which is itself stored as chained metadata
  blocks) is fetched block-by-block on demand, not eagerly for the whole
  file.
- `SingleFileBlockManager::IsRemote()` (`single_file_block_manager.cpp:1115`,
  `return !handle->OnDiskFile();`) and a dedicated
  `StorageBlockPrefetch::REMOTE_ONLY` prefetch mode
  (`single_file_block_manager.cpp:1119-1131`) show the block manager has
  code paths specifically distinguishing local-disk opens from
  remote-filesystem opens — this wouldn't exist if remote attach simply
  materialized the file locally first.
- `StorageManagerOptions::prefetched` (`single_file_block_manager.hpp`,
  comment: "Header prefetched during file-type detection; DatabaseHandle::Open
  reuses it. Empty unless opened via ATTACH.") confirms the file-type-detection
  step itself only prefetches the header, again scoped to a small fixed
  region, not the whole object.

**Practical read plan for `get_active_ciks`:** `ATTACH
's3://edgartools-prod-warehouse-690839588395/warehouse/silver/sec/silver.duckdb'
AS canonical (READ_ONLY); SELECT cik FROM canonical.sec_company_sync_state
WHERE tracking_status = 'active';` — or the even cheaper
`CREATE TABLE local.sec_company_sync_state AS SELECT * FROM
canonical.sec_company_sync_state;` to materialize just that one table
into a small local/temp file. Cost is bounded by: fixed header reads +
catalog/schema metadata (proportional to table/column *count*, ~30 tables,
not to the 1.5GB of *data*) + `sec_company_sync_state`'s own blocks (small
— it's a per-company state table, not a filing-content table). The other
~29 tables (including the multi-million-row `sec_thirteenf_holding`-class
tables) are never touched. This replaces the current
`_hydrate_silver_database_from_storage` full `read_bytes` for this one
read path.

### 2. Write: remote attach is categorically read-only — NOT FEASIBLE, confirmed explicitly by primary docs (not a version gap)

Direct quote, `docs/current/guides/network_cloud_storage/duckdb_over_https_or_s3.md`,
"## Limitations" section (verbatim, fetched from `duckdb/duckdb-web`):

> "Only read-only connections are allowed, writing the database via the
> HTTPS protocol or the S3 API is not possible."

And `docs/current/sql/statements/attach.md`:

> "`ATTACH` supports HTTP and S3 endpoints. For these, it creates a
> read-only connection by default." — followed by two `ATTACH ... (READ_ONLY)`
> examples shown as *equivalent* to the bare form, i.e. there is no
> non-read-only form for these protocols at all, not "read-only by default,
> overridable."

This is **architectural, not version-gated** — it will not change on a
DuckDB upgrade:

- DuckDB's single-file format is block-based with fixed offsets, a
  free-list, and rotating checksummed header blocks that must be updated
  consistently on every write (`single_file_block_manager.cpp`'s
  `CreateNewDatabase`/checkpoint-write paths write to `Storage::FILE_HEADER_SIZE`
  and `* 2ULL` in an alternating pattern) — this assumes local random-access,
  read-modify-write I/O to arbitrary byte offsets.
- S3's object model has no such primitive: a `PUT` replaces the entire
  object atomically; there is no S3 API for "overwrite bytes 40,000–44,096
  of an existing object in place." httpfs's S3 *write* support (confirmed
  via `docs/current/core_extensions/httpfs/s3api.md`) is real but is
  full-object, multipart-upload-based, and is exposed only for `COPY ...
  TO 's3://...'` outputs (Parquet/CSV) — never for in-place mutation of an
  already-attached database file.

So `upsert_company_sync_state`/`seed_company_sync_state_bulk` cannot write
through a remote `ATTACH` at any DuckDB version. There is no
DuckDB-native way to write "just the changed rows" into the remote
`silver.duckdb` object directly.

**What a cheaper write path *could* look like, within what's DuckDB-native today:**
combine the targeted read above with the existing local-merge machinery —
`ATTACH ... READ_ONLY`, `CREATE TABLE local.sec_company_sync_state AS
SELECT * FROM canonical.sec_company_sync_state` (small local file, not
1.5GB), apply the upsert locally, then still go through a
merge/upload/promote step. But note this only shrinks the *local materialize*
step for the write path's read-side dependency — `_publish_silver_database_if_remote`
(`warehouse_orchestrator.py:975-1048`) still fundamentally needs to
produce and upload one full replacement `silver.duckdb` object, because
that's the only unit S3 lets you write atomically and the only file
DuckDB can open as canonical next time. The full-file re-upload cost is
unavoidable **unless** `sec_company_sync_state` is split out of the
monolithic `silver.duckdb` into its own small separate file (its own
`.duckdb` or a Parquet table) attached alongside canonical — a real
structural option, but a schema/architecture decision for whoever resolves
the write-back-mechanism ticket downstream of this one, not something this
ticket is scoped to decide.

### 3. Latency/cost characteristics of a remote read against the 1.5GB file

**What the docs explicitly say (Parquet, not `.duckdb` files):**
`docs/current/core_extensions/httpfs/https.md`, "## Partial Reading":

> "For Parquet files, DuckDB supports partial reading, i.e., it can use a
> combination of the Parquet metadata and HTTP range requests to only
> download the parts of the file that are actually required by the
> query... In some cases, no actual data needs to be read at all as they
> only require reading the metadata."

**Gap to flag honestly:** the primary docs describe this partial-read
behavior explicitly for Parquet, not explicitly for `.duckdb` database
files opened via `ATTACH`. The "1" section above closes that gap with
source evidence instead (`GetBlockLocation`-offset block reads, the
`REMOTE_ONLY` prefetch mode, the three-fixed-header-block open path) — the
underlying HTTP transport (`handle->Read(context, block, location)`) is
the same httpfs file-handle abstraction used for every remote file type,
so the range-request mechanism applies the same way; it's an inference
from the actual implementation, not a literal doc quote, which is why it's
called out separately here rather than folded into "1." as a doc-confirmed
fact.

**Conclusion:** querying `sec_company_sync_state` does **not** require
reading a large fraction of the 1.5GB file's metadata or catalog structures.
Header + catalog + schema metadata is small and roughly constant in table
*count*, not data *volume*; the query then touches only the target table's
own blocks. This is genuinely cheap relative to the current full-file
`read_bytes`, which is exactly the OOM-causing behavior in
`_hydrate_silver_database_from_storage` (`warehouse_orchestrator.py:938-972`,
`payload = read_bytes(remote_path)` unconditionally loading the whole
object into process memory before `local_path.write_bytes(payload)`).

### 4. Concurrent-access caveat — real, and directly relevant given this repo already writes full-file replacements

`docs/current/core_extensions/httpfs/s3api.md`, "### Pinning Object Versions"
(verbatim):

> "By default, a long-running query re-reads an object at whatever version
> is current at read time, which can change if the object is overwritten.
> Set `s3_version_id_pinning` (`BOOLEAN`, default `false`) to pin reads to
> the object version captured on the first `HEAD` request, so a query sees
> a consistent version even if the object is overwritten mid-query. This
> requires the HTTP metadata cache."

So the default httpfs behavior is **not** safe against a concurrent writer
mid-query — a query could read the header/catalog from one version of
`silver.duckdb` and table data blocks from a different, concurrently
promoted version, since separate range GETs aren't otherwise pinned to one
object version. This is a direct parallel to the exact race this repo's
own `_publish_silver_database_if_remote` already guards against with
`context.storage_root.read_object_version` + promotion-conflict checks
(`warehouse_orchestrator.py:976-988`) — any adoption of remote `ATTACH`
reads must either set `enable_http_metadata_cache = true` +
`s3_version_id_pinning = true` (requires S3 bucket versioning enabled on
`edgartools-prod-warehouse-690839588395` — not verified as part of this
ticket, should be confirmed before relying on it) or accept that a read
racing a publish could, in principle, see an inconsistent mix. For a
read-only, best-effort skip-list use (`get_active_ciks` deciding what to
re-bootstrap) an inconsistent read is a low-severity risk (worst case:
briefly wrong skip decision, self-correcting next run) — but should be an
explicit, named tradeoff if adopted, not a silent gap.

### 5. Credentials/IAM — same underlying permissions, different in-process configuration surface

`edgar_warehouse/infrastructure/object_storage.py` uses `boto3.client("s3")`
(`_s3()`, line ~130) and `fsspec.filesystem(protocol, **_remote_storage_options(...))`
(`_remote_storage_options` currently returns `{}` — no explicit credentials
passed at all) — both rely entirely on boto3's ambient credential chain
(ECS task role via the container credentials endpoint), zero in-repo
credential configuration.

httpfs does **not** automatically inherit that. Per
`docs/current/guides/network_cloud_storage/s3_import.md` and
`docs/current/core_extensions/aws.md`, a DuckDB connection needs its own,
explicit one-time setup:

```sql
-- httpfs and aws both autoload on first s3:// use per
-- docs/current/core_extensions/aws.md ("Installing and Loading"), but can
-- also be installed/loaded explicitly:
INSTALL httpfs; LOAD httpfs;
CREATE SECRET (TYPE s3, PROVIDER credential_chain);  -- delegates to the AWS SDK's
                                                       -- standard chain, which resolves
                                                       -- the same ECS task role boto3 uses
ATTACH 's3://.../silver.duckdb' AS canonical (READ_ONLY);
```

Two real, non-blocking differences from the existing pattern to plan for,
not IAM-policy changes (no new grants needed — same bucket, same
`GetObject` permission the task role already has for `read_bytes`):

- **No new IAM policy required** — `PROVIDER credential_chain` walks the
  same AWS SDK credential resolution order that ultimately finds the ECS
  task role, same as boto3.
- **Per-session, not persistent.** `docs/current/sql/statements/attach.md`:
  "Note that attachment definitions are not persisted between sessions:
  when a new session is launched, you have to re-attach to all databases."
  Secrets are the same — every process invocation (every ECS task run)
  must redo `CREATE SECRET` + `ATTACH`, unlike boto3/fsspec which need zero
  setup calls today. This is a small, one-time code addition, not an
  operational blocker.
- **Extension download dependency.** `httpfs`/`aws` autoload from DuckDB's
  public extension repository on first use unless pre-installed into the
  image. Since this ECS task already reaches the public internet (SEC
  EDGAR API calls), this is very likely a non-issue, but worth confirming
  the image/network path allows reaching DuckDB's extension CDN, or
  pre-baking the extensions into the warehouse image to avoid a runtime
  network dependency.

## Verdict

**Partially feasible: feasible for read, not feasible for write.**

- **Read (`get_active_ciks` / any read-only query against
  `sec_company_sync_state` or other small tables):** genuinely feasible
  without downloading/materializing the full 1.5GB `silver.duckdb` —
  `ATTACH 's3://.../silver.duckdb' AS canonical (READ_ONLY)` plus a
  targeted `SELECT`/`CREATE TABLE AS SELECT` against exactly the table
  needed, confirmed by both DuckDB's documented `ATTACH` behavior and its
  block-level storage implementation. Requires new one-time-per-process
  DuckDB extension/secret setup (no new IAM), and should set
  `s3_version_id_pinning` (+ confirm bucket versioning) if read-during-concurrent-write
  consistency matters for the caller.
- **Write (`upsert_company_sync_state`, `seed_company_sync_state_bulk`):**
  not feasible via remote attach at any DuckDB version — confirmed
  explicitly and unambiguously by DuckDB's own docs ("writing the database
  via the HTTPS protocol or the S3 API is not possible"), and this is an
  architectural property of both DuckDB's block-based single-file format
  and S3's whole-object-PUT model, not a missing feature that a version
  bump would add. The write path must keep going through the existing
  full-hydrate → local merge → full-file upload → version-checked promote
  flow (`_hydrate_silver_database_from_storage` /
  `_publish_silver_database_if_remote`), *or* the platform makes a
  structural change (splitting `sec_company_sync_state` — and potentially
  other small, frequently-written tables — out of the monolithic
  `silver.duckdb` into its own small file attached alongside canonical, so
  a future write only has to replace that small object, not the 1.5GB
  whole). That structural option is real and DuckDB-native (multi-database
  `ATTACH` across separate files is ordinary DuckDB usage, no different
  from `stations_db` in the docs' own examples), but it's a design decision
  for the write-back-mechanism ticket this one blocks, not something
  resolved here.
