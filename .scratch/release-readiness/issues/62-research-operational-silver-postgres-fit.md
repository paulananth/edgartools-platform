# Research whether PostgreSQL is the right scalable operational Silver store

Type: research
Status: resolved
Blocked by: (none)

## Question

For the AWS-first SEC EDGAR platform, should canonical operational Silver move
from its S3-backed DuckDB publication model to PostgreSQL in order to improve
daily-load speed and scalability, or is a smaller change (the new run-scoped
reducer, durable artifact resume, sharding, or another store) the better
remedy?

## Required evidence

- Measure the current production path's real bottlenecks separately: S3
  hydration/publication, DuckDB merge cost, SEC fetch rate, artifact candidate
  selection, retry amplification, and downstream MDM/gold access.
- Compare PostgreSQL with retained DuckDB and at least one credible AWS-native
  alternative on write concurrency, transactional/conditional-publication
  semantics, analytical scan workload, S3/Snowflake integration, operational
  cost, recovery, and migration risk.
- Do not assume Postgres is faster merely because it accepts concurrent writes;
  distinguish OLTP row updates from the large analytical tables and export
  workloads.
- Produce a falsifiable recommendation with threshold metrics and the smallest
  next experiment or implementation decision. No database migration, schema
  change, or production workload mutation belongs in this research ticket.

## Done when

The platform has an evidence-backed keep/hybrid/migrate recommendation and an
explicit follow-up decision or task only if the evidence warrants one.

## Answer (2026-08-01)

**Recommendation: do not move canonical operational Silver to PostgreSQL
now.** Keep the S3-backed DuckDB Silver artifact and its one-promotion
run-scoped reducer; add only the small durable operational ledger required by
the already-open Daily Artifact resume/disposition decision. PostgreSQL is not
the current critical path, and a full migration would be a large new system of
record plus a new Snowflake/export/recovery path before it could improve the
daily SLA.

### Measured bottlenecks versus the proposed remedy

| Current bottleneck | Direct production evidence | Would PostgreSQL fix it? | Better next action |
| --- | --- | --- | --- |
| Identity publication | A 500-CIK batch previously spent about 32m45s merging and publishing the 1.07-GB canonical artifact; local application was 52.51s. | It would remove file-level replacement, but at the cost of a full store/schema/loader/export/recovery rewrite. | Validate the deployed run-scoped reducer, which reduces this to one verified publication per run. |
| Daily artifacts | 5,120 of 5,122 candidates took 2h41m54s and 40,728 SEC fetches; a generic task retry repeated the whole pass. | No: the dominant work is SEC/network capture and the missing resume contract. | Complete the durable per-accession ledger/disposition decision before changing the data store. |
| Batch write path | The historical row-by-row filing merge was the expensive path, but it has been replaced by staged set-based upsert. | Unknown until the repaired path is measured. | Measure the current bulk path before substituting an engine. |
| Analytical serving | Silver feeds Parquet exports and Snowflake native pull; the largest known 13F relation is multi-million-row analytical data. | PostgreSQL would add another extract/export copy and is not the serving warehouse. | Keep Snowflake/Parquet as analytical serving. |

DuckDB documents that native database-file multi-writer concurrency is within a
single process; PostgreSQL MVCC does support concurrent transactional sessions.
That advantage is real, but this platform's current daily design intentionally
serializes canonical identity publication and the present failing work is not
that publication. Sources: [DuckDB concurrency](https://duckdb.org/docs/current/connect/concurrency),
[PostgreSQL MVCC](https://www.postgresql.org/docs/current/mvcc-intro.html).

### Bounded hybrid, not a second Silver source of truth

- Retain canonical Silver in S3-backed DuckDB, the run-bound deltas/reducer,
  and Snowflake-native Parquet export.
- Make the durable artifact candidate/outcome ledger a narrow operational
  component of the pending resume/disposition contract, not a migration of all
  Silver facts and dimensions to Postgres.
- PostgreSQL/Aurora is worth a controlled comparison only if the platform
  develops more than one independent low-latency transactional writer. It has
  meaningful concurrency capability, but it needs normal connection, vacuum,
  capacity, backup, and export operations; it is not a free speed upgrade.
- If future evidence calls for multi-engine analytical tables, compare an
  Iceberg/S3 Tables design before PostgreSQL. That serves a different (large
  analytic/lake-table) need, not the current daily retry defect. AWS itself
  distinguishes row-oriented OLTP and column-oriented OLAP engines:
  [Redshift and PostgreSQL](https://docs.aws.amazon.com/redshift/latest/dg/c_redshift-and-postgres-sql.html).

### Falsifiable gate

Keep DuckDB unless post-fix evidence shows one of the following:

1. After the run-scoped reducer and durable artifact-resume contract are live,
   three immutable-image daily runs have p95 reducer
   hydrate/merge/publish cost above 90 minutes **or** above 25% of total daily
   elapsed time; or
2. the product requires more than one independent low-latency transactional
   writer to canonical operational data.

Choose PostgreSQL only after an isolated benchmark demonstrates at least a
2x lower **end-to-end daily elapsed time** (not merely faster upserts), while
preserving immutable run inputs, fail-closed conflict semantics, recovery, and
the existing Snowflake export contract. If the demonstrated need is instead
multi-engine analytic scans, concurrent batch writes, time travel, and table
evolution, evaluate Iceberg/S3 Tables first.

### Smallest next experiment

Do not provision a production database. First benchmark a copied 1.07-GB
Silver snapshot plus representative run deltas read-only: separately capture
S3 download/upload, DuckDB merge CPU/wall time, delta size, and promotion
duration. Only if publication remains material should a disposable PostgreSQL
benchmark run the same identity-upsert workload and compare key-level checksums,
row counts, Parquet-export time, and end-to-end elapsed time.

No new follow-up ticket is needed now: the immediate work is already tracked
by [Implement run-scoped Daily Identity Refresh publication](61-implement-run-scoped-daily-identity-publication.md)
and [Decide a Durable Daily-Artifact Resume and Disposition Contract](60-decide-durable-daily-artifact-resume-disposition.md).
