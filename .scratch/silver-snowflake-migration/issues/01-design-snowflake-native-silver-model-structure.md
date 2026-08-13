# Design the Snowflake-Native Silver Layer's Model Structure

Type: grilling
Status: resolved
Blocked by: none

## Question

How does data flow from bronze through Snowflake-native silver to gold once
Python's SEC-document parsing (unavoidable — see map Notes) lands rows in a
new Snowflake landing zone instead of a local `silver.duckdb`?

Specify: the landing-zone schema (raw parsed rows, pre-clean/dedupe) versus
final silver table shape; which existing silver tables (per
`edgar_warehouse/silver_store.py`) map to incremental dbt models versus
snapshot-style models, given SEC filings are additive/immutable once
captured (per CLAUDE.md's "SEC data idempotency" policy — silver's
clean/dedupe logic must still express that same immutability guarantee in
dbt/Snowflake terms); how bronze's existing native-S3-pull-into-SOURCE
pattern does or doesn't extend to silver's landing zone (silver's raw input
requires Python parsing first, unlike SOURCE's already-structured parquet);
and where the CIK-scoped/company-scoped partitioning that today's shard
manifest (`edgar_warehouse/application/sharding/`) provides gets expressed,
if at all, once Snowflake's storage model replaces file-based sharding.

This is the map's priority ticket — `load_history`'s retry6 is blocked on
this ticket reaching a locked answer, not on the full migration being
built.

## Answer

Locked model structure, in four decisions plus the design detail each one
implies. Grounded in a fresh three-angle investigation of the current
system (not carried over from prior maps): `silver_store.py`'s actual
write patterns (43 DDL tables, 31 protected/domain, 13 excluded/
operational), the sharding manifest's storage-vs-concept split, gold's
raw-SQL read pattern, and `EDGARTOOLS_SOURCE`'s existing native-pull
mechanism — which turned out to be a live precedent this ticket both
reuses and deliberately diverges from.

**Correction to this ticket's own framing, surfaced by the investigation:**
"SEC filings are additive/immutable" (the premise in this ticket's
Question) describes bronze, not today's silver. `silver_store.py` is
overwhelmingly upsert-by-natural-key — 24 of 31 protected tables split
columns into first-insert-wins vs. last-write-wins halves
(`_merge_rows_bulk`), and only one table (`sec_guidance_fact_reject`) is
genuinely append-only. The new architecture below restores the honest
append-only/immutable property at the landing zone specifically — silver
itself stays current-state, matching what gold already expects.

### 1. Landing-zone schema: append-only, new schema, reused ingest apparatus

A new schema, `EDGARTOOLS_SILVER_LANDING`, holds one table per parsed
domain table, **append-only**: every parse event writes a new row keyed
by `(business_key_columns..., parse_sequence)`, nothing is ever updated
or deleted. This is deliberately distinct from `EDGARTOOLS_SOURCE`, which
already serves a different purpose today (a current-state MERGE mirror
fed from gold-adjacent Parquet passthroughs, per
`infra/snowflake/sql/bootstrap/03_source_load_wrapper.sql`) — conflating
the two would silently change SOURCE's contract for its existing
consumers.

Ingest reuses `EDGARTOOLS_SOURCE`'s existing apparatus **verbatim in
shape, simplified in mechanism**: Python writes per-table Parquet +
`run_manifest.json` to S3 → Snowpipe auto-ingest of the manifest only →
stream + task → a load procedure that stages via `TEMP TABLE ... LIKE
target` + `COPY INTO`, row-count-validated against the manifest (fail
closed on mismatch, same as today). The divergence: because landing is
append-only, the load procedure needs no `mergeKeys` map at all for these
tables — a plain `INSERT INTO target SELECT * FROM staged` replaces
`LOAD_EXPORTS_FOR_RUN`'s `MERGE` branch for every landing table. This is
strictly simpler than what SOURCE's loader does today, not an extension
of its complexity.

### 2. Final silver shape: uniformly `dynamic_table`, current-state — not a per-table incremental/snapshot mix

This ticket's own Question asked which tables map to "incremental dbt
models versus snapshot-style models." The honest answer, once the
landing zone is append-only and every table needs to present the same
current-state/one-row-per-business-key shape gold already consumes
(confirmed: 20 silver tables read directly by name across every
`_build_*` function in `gold_models.py`): **neither, uniformly.** Every
final silver table is a `dynamic_table` (`TARGET_LAG = DOWNSTREAM`),
exactly matching gold's own existing convention (21 of 23 gold models
already use this; zero incremental models exist anywhere in this dbt
project).

This was reconsidered explicitly against `materialized='incremental'`
before locking. Decisive factor: `dynamic_table` requires `dbt run` only
once, at deploy time, to create the object — thereafter Snowflake's own
engine refreshes it natively. `incremental` models require an external
process to invoke `dbt run` on an ongoing basis for the life of the
pipeline, and **no automated `dbt run` invocation exists anywhere in this
platform today** (verified live: CI only runs `dbt parse`/compile-check;
`deploy-snowflake-stack.sh --run-dbt` and `install.sh` are human-invoked,
gated/one-time; zero ECS task, Step Functions state, or Dockerfile
references `dbt` anywhere). Choosing `incremental` would have made this
migration responsible for designing and building that trigger
infrastructure from scratch as a side effect of a model-structure
decision. Choosing `dynamic_table` means silver's tables simply join
`REFRESH_AFTER_LOAD`'s existing allowlist (`infra/terraform/snowflake/
modules/native_pull/sql/refresh_procedure.sql`'s `goldTables`-equivalent)
alongside gold's — refreshed in the same already-live chain, right after
landing loads and right before gold refreshes. No new orchestration
surface. (Noted, not a design blocker: Snowflake's dynamic-table refresh
may fall back to full-table recompute rather than true incremental
refresh for `ROW_NUMBER()`-shaped dedup queries — a cost/latency question
to measure once real volume exists, not a correctness one; a dynamic
table is always correct regardless of which refresh path Snowflake
picks.)

**Column-level first-insert-wins/last-write-wins expression**, for the 24
tables that need it (matching today's `_merge_rows_bulk` split, e.g.
`sec_company_filing`, `sec_financial_fact`): each dynamic table's
defining query uses two window-function passes over the append-only
landing table — `QUALIFY ROW_NUMBER() OVER (PARTITION BY &lt;key&gt; ORDER BY
parse_sequence ASC) = 1` for the immutable-on-conflict columns, `... ORDER
BY parse_sequence DESC = 1` for the mutable columns — combined by key.
This is exactly the "no authority column" problem
(`silver_protection.py`'s 17-of-31 tables with no tiebreak) resolved
structurally: with full parse history visible in landing, `parse_sequence`
is a uniform, deterministic tiebreak for every table, replacing the
per-table `authority_column` convention (and its associated fail-closed
`SemanticMergeConflictError` behavior) entirely.

**Two named special cases**, not silently absorbed into the uniform
pattern:
- `sec_guidance_fact_reject` — stays append/log-shaped in silver too (a
  view over landing, not a collapsed dynamic table); it's a quarantine
  log by design, not a domain entity with a current state.
- `sec_company_ticker` (delete-by-`source_name`) and
  `sec_company_former_name`/`sec_company_submission_file`
  (delete-by-`cik`) — today's actual write path is coarser than their
  declared primary key (see investigation finding: `sec_company_ticker`'s
  DDL/registry key is `(cik, ticker, source_name)` but the write path
  replaces by `source_name` alone). Silver's dynamic table expresses this
  the same way as every other current-state table (latest row per the
  declared key, via the window-function pattern above) — the
  delete-then-insert mechanic was solely a DuckDB implementation detail
  for enforcing "remove rows the latest sync no longer reports," not a
  business rule that needs its own dbt shape; an append-only landing zone
  makes that removal semantics moot; a row simply stops being latest.

### 3. CIK-scoped/company-scoped partitioning: explicitly deferred, not resolved here

The sharding manifest's file mechanics (checksums, hydrate/publish,
`ShardedSilverReader`'s `UNION ALL` reconstruction, the
`shard_window_crosses_band_boundary` avoidance dance) are purely
file-storage plumbing and do not survive into Snowflake in any form —
confirmed via direct investigation, not assumed. But three things do need
some analog and are **not** decided by this ticket: CIK as a
clustering/pruning key, the 100-CIK-batch unit-of-work for the
Distributed Map, and the three-way table taxonomy (CIK-direct /
accession-join-by-issuer / CRD-keyed-global, the last of which exists
specifically because `sec_adv_filing.cik` is NULL for 58,598/58,599
production rows — advisers are CRD-keyed via IAPD, not CIK-keyed, and
losing this fact would silently reintroduce that bug in a new guise).
This is [Confirm Relationship to `pipeline-throughput-architecture`'s
Sharding Work](06-confirm-relationship-to-sharding-work.md)'s explicit
job, not this ticket's — flagging here only so a future reader doesn't
assume it was silently dropped.

### 4. Explicitly out of scope for this ticket

The 13 excluded-operational tables (`schema_migration`, checkpoints,
`pipeline_run_lease`, parse-run/sync-run logs, `gold_manifest`) are
warehouse-runtime bookkeeping, not canonical multi-writer domain data —
they are not part of the landing → silver → gold pipeline this ticket
specifies. Several of them (notably `pipeline_run_lease` and the
promotion-retry machinery it protects) exist specifically to solve a
whole-file-DuckDB-swap concurrency problem
(`_publish_silver_database_with_retry`, unbounded retry since the
2026-07-22 regression) that this architecture may obsolete outright, since
Snowflake's native transactional guarantees replace the ETag-swap
mechanism entirely. Their disposition — retire, keep as local runtime
state, or replace with a Snowflake-native equivalent — is [Decide the
Concurrent-Writer Model for Snowflake-Native
Silver](02-decide-concurrent-writer-model.md)'s job, now unblocked by
this answer.

**Net:** `Bronze (S3 Parquet, unchanged) → EDGARTOOLS_SILVER_LANDING`
(new schema, append-only, reused ingest apparatus, simplified to
plain-INSERT) `→ dbt dynamic_table silver models` (current-state,
window-function collapse, join the existing `REFRESH_AFTER_LOAD` chain)
`→ EDGARTOOLS_GOLD` (unchanged SQL, only its connection source moves from
DuckDB to Snowflake — confirmed a drop-in swap at the `get_connection`/
`conn.execute` seam). No new orchestration infrastructure required.
