# Snowflake incremental change-processing primitives

Research date: 2026-08-20

Scope: current official Snowflake documentation only. The conclusions below
apply to the Incremental Change Propagation Wayfinder map; they do not specify
implementation details outside Snowflake.

## Decision summary

Snowflake has the necessary primitives for incremental landing and publication,
but none of them alone proves a run-bound, cross-stage publication barrier.
The safe composition is:

1. immutable, content-addressed S3 delta files whose rows carry the Change
   Propagation Run identity and explicit `UPSERT`, `RETIRE`, or
   `SCOPE_COMPLETE` semantics;
2. append-only landing plus one independent stream per consumer;
3. deterministic `MERGE` and a stage outcome written in one explicit DML
   transaction;
4. an explicitly selected dynamic-table dependency closure, refreshed at one
   shared data timestamp and checked per table; and
5. a durable application-owned run ledger that records the Snowflake evidence
   and publishes the Decision Watermark only after every expected stage has
   succeeded.

`COPY INTO` history, stream offsets, task history, and dynamic-table refresh
history are corroborating evidence. They have retention, latency, identity, or
atomicity limits that make them unsuitable as the sole authoritative run
ledger.

## 1. `COPY INTO` file identity and retry behavior

Snowflake stores per-target-table load metadata including the source filename,
file size, ETag, parsed-row count, last-load time, and errors. That metadata
expires after 64 days; when identity is uncertain for an older file, `COPY`
skips it by default. `LOAD_UNCERTAIN_FILES = TRUE` tries files whose status is
unknown, while `FORCE = TRUE` ignores load metadata and can duplicate rows.
[Loading data](https://docs.snowflake.com/en/user-guide/data-load-considerations-load)
documents the metadata and expiration rules, and
[`COPY INTO <table>`](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table)
documents the two override options.

By default, a previously loaded staged file is ignored. Modifying and staging a
file again generates a new checksum and makes it loadable; forcing an unchanged
file explicitly reloads it and duplicates its rows.
[`COPY INTO <table>` usage notes and reload example](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table#usage-notes)
therefore establish that an overwritten S3 key is not a correction primitive:
changed bytes can be ingested as another load, but Snowflake does not retract
the rows loaded from the previous bytes.

Bulk-load deduplication is also tied to the target table object. Dropping or
recreating the target clears the relevant load-history metadata.
[`COPY_HISTORY` Account Usage view](https://docs.snowflake.com/en/sql-reference/account-usage/copy_history)

### Consequences for this design

- Never overwrite a delta object to correct it. Use a new immutable key that
  includes a content hash or immutable S3 version identity, and link it to the
  superseded event in the run manifest.
- Do not use `COPY`'s 64-day metadata as the durable idempotency contract. Put a
  stable event/change identity in every row and enforce idempotency again in
  the publication `MERGE` or application ledger.
- A correction must arrive as an explicit later `UPSERT`, `RETIRE`, or
  `SCOPE_COMPLETE` event. Loading corrected file bytes cannot infer which
  previously loaded business rows should disappear.
- `FORCE = TRUE` belongs only in a controlled repair whose row-level
  idempotency has already been proved; it is unsafe as normal replay behavior.

## 2. Streams and tasks

A standard stream exposes the minimal row-level change set between its offset
and the current table version. It tracks inserts, updates, and deletes; an
update is represented by a DELETE/INSERT pair with `METADATA$ISUPDATE = TRUE`.
The result is a net delta, so a row inserted and then deleted between offsets
does not appear. A stream stores an offset, not data, and advances only when it
is consumed in a committed DML transaction.
[Introduction to streams](https://docs.snowflake.com/en/user-guide/streams-intro)

An append-only stream records only inserts and omits update, delete, and
truncate operations. Insert-only streams on external tables likewise do not
report removals: replacing an external file yields inserts for the new file but
no delete records or old-versus-new diff.
[Stream types](https://docs.snowflake.com/en/user-guide/streams-intro#types-of-streams)

Streams depend on source Time Travel/change-retention history. Once a stream is
stale, unconsumed records can be inaccessible and the stream must be recreated.
Recreating a source table also makes its stream stale.
[Stream staleness](https://docs.snowflake.com/en/user-guide/streams-intro#data-retention-period-and-staleness)

`SYSTEM$STREAM_HAS_DATA` is designed to avoid false negatives for a non-stale
stream, but it can return false positives. Snowflake requires a DML consumption
to advance the offset even after such a false positive.
[`SYSTEM$STREAM_HAS_DATA`](https://docs.snowflake.com/en/sql-reference/functions/system_stream_has_data)

Triggered tasks serialize instances of the same task, but task history can
contain duplicated task executions during a cloud-services failure. Triggered
tasks are therefore a wake-up/serialization primitive, not an exactly-once
guarantee.
[Triggered-task execution rules](https://docs.snowflake.com/en/user-guide/tasks-triggered#allow-a-triggered-task-to-run)
and [`TASK_HISTORY` usage notes](https://docs.snowflake.com/en/sql-reference/functions/task_history#usage-notes)

### Consequences for this design

- The landing table should be append-only and encode retirement/replacement as
  explicit inserted change records. An append-only stream is then valid and
  efficient because "delete" is domain data, not a physical landing-table
  DELETE. A standard stream is required if the landing table itself is mutable.
- Give silver, MDM, gold, and any audit consumer their own stream. A shared
  offset would couple independent publication and replay lifecycles.
- Consume a stream and write the target plus stage outcome in a committed DML
  transaction. Retries and duplicate task invocations must remain harmless by
  stable event identity.
- Monitor `STALE_AFTER` and retention headroom; stream history is not the
  long-term replay source. Immutable S3 manifests remain that source.

## 3. `MERGE` and transactional boundaries

`MERGE` natively supports matched UPDATE or DELETE and unmatched INSERT, so it
can publish upserts and retirement state from a change log.
[`MERGE`](https://docs.snowflake.com/en/sql-reference/sql/merge)

When multiple source rows match one target row, update/delete behavior can be
nondeterministic. The default `ERROR_ON_NONDETERMINISTIC_MERGE = TRUE` fails
those ambiguous merges; Snowflake recommends reducing the source to at most one
row per target key.
[`MERGE` duplicate join behavior](https://docs.snowflake.com/en/sql-reference/sql/merge#duplicate-join-behavior)

Snowflake treats DML statements, including `MERGE`, as transactions. A
successful statement outside an explicit transaction is atomically committed;
multiple DML/query statements can be committed or rolled back together in one
explicit transaction. DDL implicitly commits an active transaction and then
runs as its own transaction.
[Snowflake transactions](https://docs.snowflake.com/en/sql-reference/transactions)

### Consequences for this design

- Reduce each run's source to one authoritative event per business key before
  `MERGE`, using the accepted monotonic source-version rule. Leave
  `ERROR_ON_NONDETERMINISTIC_MERGE` enabled so same-identity/different-content
  conflicts fail closed.
- The target `MERGE`, consumption of the stream offset, and insertion of the
  Snowflake stage-outcome row can share one explicit DML transaction. The
  procedure/controller must roll back the transaction on any statement error;
  Snowflake permits a caller to commit other successful statements after one
  DML statement fails, so failure handling cannot be implicit.
- Do not mix DDL into that transaction. Dynamic-table manual refresh also
  cannot be included in it, as described below.

## 4. Dynamic-table refresh scope and observability

Snowflake currently exposes `ADAPTIVE`, `INCREMENTAL`, `FULL`, and `AUTO`
managed modes plus custom incrementalization. Incremental refresh analyzes
changed data and merges its effect; full refresh recomputes and replaces the
entire result. `AUTO` resolves once at creation to incremental or full and then
stays fixed. `ADAPTIVE` normally refreshes incrementally but may reinitialize
when Snowflake judges incremental work more expensive.
[Dynamic-table refresh modes](https://docs.snowflake.com/en/user-guide/dynamic-tables/refresh-modes)

Production DDL should therefore declare a mode rather than depend on `AUTO`.
If any full recomputation is forbidden, use `INCREMENTAL` and accept a creation
failure for unsupported constructs. If bounded normal work with observable
occasional rebuilds is acceptable, `ADAPTIVE` is the current Snowflake-recommended
mode for incrementalizable workloads, and every `REINITIALIZE` must be recorded
as such.
[Mode selection and observability](https://docs.snowflake.com/en/user-guide/dynamic-tables/refresh-modes#choose-a-refresh-mode)

Snowflake can manually refresh multiple named dynamic tables in one statement.
It merges their upstream dependencies into one pipeline, refreshes a shared
upstream once, and evaluates all refreshed tables at the same `DATA_TIMESTAMP`.
This provides a native way for an external controller to name an affected set
of leaf tables and refresh their upstream closure instead of requesting every
dynamic table in the account.
[Refresh multiple dynamic tables](https://docs.snowflake.com/en/user-guide/dynamic-tables/manage#refresh-multiple-dynamic-tables-in-one-statement)

That multi-table refresh is not atomic. Successfully refreshed tables remain
published when another table fails, and manual refresh is not allowed inside a
multi-statement transaction. The caller must query refresh history for the
shared `DATA_TIMESTAMP`, verify each expected table, and retry only failed or
missing tables.
[Multi-table refresh partial failures](https://docs.snowflake.com/en/user-guide/dynamic-tables/manage#partial-failures)

`DYNAMIC_TABLE_GRAPH_HISTORY` exposes each dynamic table's base/dynamic-table
inputs and graph-version validity, enabling the controller to calculate and
freeze the expected dependency closure for a run.
[`DYNAMIC_TABLE_GRAPH_HISTORY`](https://docs.snowflake.com/en/sql-reference/functions/dynamic_table_graph_history)

`DYNAMIC_TABLE_REFRESH_HISTORY` exposes `STATE`, `QUERY_ID`, `DATA_TIMESTAMP`,
refresh start/end, the last completed dependency, row/partition statistics,
`REFRESH_ACTION` (`NO_DATA`, `REINITIALIZE`, `FULL`, `INCREMENTAL`, or
`CUSTOM_INCREMENTAL`), the trigger, and the graph version used.
[`DYNAMIC_TABLE_REFRESH_HISTORY` columns](https://docs.snowflake.com/en/sql-reference/account-usage/dynamic_table_refresh_history#columns)

For deployments that later choose Snowflake-native dbt project objects,
`EXECUTE DBT PROJECT` supports dbt `run`/`build` with `--select`, so a caller can
name a model slice and its dbt graph relationships. A single dbt project object
does not support concurrent `EXECUTE DBT PROJECT` calls, even with disjoint
selectors; they must be serialized or use separately deployed project objects.
[Supported dbt commands and flags](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-supported-commands)
and [dbt project concurrency limits](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-limitations)

### Consequences for this design

- The affected dbt DAG is a controller/dbt selection decision. Snowflake can
  execute the selected dynamic-table closure, but it does not infer which gold
  products are semantically affected by a Change Propagation Run.
- Preserve the repository's existing dbt execution architecture unless a
  separate decision changes it. If Snowflake-native dbt project objects are
  adopted later, pass a frozen `--select` expression and serialize executions
  per project object; record the resolved node set from dbt artifacts rather
  than treating the selector string alone as proof.
- "Bounded DAG" means bounded table dependencies. For a normal managed dynamic
  table, the internal engine decides which changed rows/partitions must be read;
  a caller cannot pass an arbitrary business-key predicate to the refresh.
  This is an inference from the documented refresh API. If strict key-bounded
  execution is required, materialize a run-scoped affected-key relation and use
  explicit/custom `MERGE` logic rather than claiming managed refresh performed
  only those keys.
- Persist, for every selected table, its resolved refresh mode, actual
  `REFRESH_ACTION`, state, query ID, statistics, graph version, and shared data
  timestamp. `numCopiedRows` and partition statistics are important evidence
  that a logically small change did not trigger unexpectedly broad work.
- Treat `FULL` or `REINITIALIZE` as observable fallback outcomes, not silent
  incremental success. A policy gate can accept, warn, or reject them by table.
- A shared `DATA_TIMESTAMP` aligns Snowflake tables but does not make the batch
  atomic. Do not publish the Decision Watermark until all expected rows in the
  application run ledger say the selected closure succeeded.

## 5. Native history surfaces and the run barrier

The useful native evidence surfaces are:

| Surface | Useful identity/evidence | Important limit |
| --- | --- | --- |
| `INFORMATION_SCHEMA.COPY_HISTORY` | file/path, stage, target, load status, row counts, errors | 14-day history; completed `COPY` only; target recreation removes bulk history. [Official reference](https://docs.snowflake.com/en/sql-reference/functions/copy_history) |
| `ACCOUNT_USAGE.COPY_HISTORY` | same file-level evidence across bulk `COPY` and Snowpipe | 365 days but normally up to two hours latency, potentially longer for low-volume tables. [Official reference](https://docs.snowflake.com/en/sql-reference/account-usage/copy_history) |
| `INFORMATION_SCHEMA.TASK_HISTORY` | query ID, state, timestamps, graph/version/run IDs, attempt, return value, trigger | seven days; task duplicates can appear during cloud-service failure. [Official reference](https://docs.snowflake.com/en/sql-reference/functions/task_history) |
| `INFORMATION_SCHEMA.COMPLETE_TASK_GRAPHS` | whole-graph state, `GRAPH_RUN_GROUP_ID`, attempt, config, first error | only completed graph runs from the past 60 minutes. [Official reference](https://docs.snowflake.com/en/sql-reference/functions/complete_task_graphs) |
| `INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY` | current/completed state and the shared data timestamp | seven days. [Official reference](https://docs.snowflake.com/en/sql-reference/functions/dynamic_table_refresh_history) |
| `ACCOUNT_USAGE.DYNAMIC_TABLE_REFRESH_HISTORY` | durable refresh action/statistics/state | Account Usage historical retention is 365 days; this view can have up to three hours latency. [View reference](https://docs.snowflake.com/en/sql-reference/account-usage/dynamic_table_refresh_history) and [Account Usage retention](https://docs.snowflake.com/en/sql-reference/account-usage) |
| `DYNAMIC_TABLE_GRAPH_HISTORY` | topology, inputs, graph validity interval | Information Schema graph descriptions are limited to the recent seven-day window. [Official reference](https://docs.snowflake.com/en/sql-reference/functions/dynamic_table_graph_history) |
| `DBT_PROJECT_EXECUTION_HISTORY` (only if Snowflake-native dbt project objects are used) | query ID, command, selector arguments, state, dbt/adapter versions, artifact locator | seven days in Information Schema; 365 days with up to two hours latency in Account Usage. [Official reference](https://docs.snowflake.com/en/sql-reference/account-usage/dbt_project_execution_history) |

For Snowflake task graphs, a controller can pass a Change Propagation Run ID in
per-execution JSON using `EXECUTE TASK ... USING CONFIG`; tasks can read it with
`SYSTEM$GET_TASK_GRAPH_CONFIG`. The same graph execution exposes a
`GRAPH_RUN_GROUP_ID`, and the combination of graph-run group and attempt
identifies an execution attempt.
[Task graph runtime configuration](https://docs.snowflake.com/en/user-guide/tasks-graphs#create-a-task-graph-with-logic-runtime-info-configuration-and-return-values)
and [`SYSTEM$TASK_RUNTIME_INFO`](https://docs.snowflake.com/en/sql-reference/functions/system_task_runtime_info)

### Barrier contract supported by these primitives

For each Snowflake stage, persist an application-owned outcome keyed by
`change_run_id`, stage, producer, and attempt. The outcome should record:

- the expected immutable file/version/hash set and corresponding successful
  copy rows;
- the stream/source offset or source-version boundary consumed;
- the target publication transaction/query identity and inserted, updated,
  retired, unchanged, and conflict counts;
- the frozen dynamic-table closure and graph version;
- one shared dynamic-table `DATA_TIMESTAMP`, plus a successful row and actual
  refresh action/statistics for every expected table; and
- reconciliation assertions proving no expected producer or affected key is
  missing.

The Decision Watermark may advance only after these durable application-owned
outcomes are complete. Native histories are linked evidence and recovery aids,
not the watermark itself: bulk-copy metadata expires, Information Schema
history is short-lived, Account Usage is delayed, task execution can be
duplicated, and a multi-table refresh can publish partially.

## Wayfinder decisions enabled by this research

1. Use immutable content-addressed delta keys and row-level event identity;
   never model an overwritten key or `FORCE` reload as a correction.
2. Use append-only landing with explicit lifecycle operations, one stream per
   consumer, deterministic `MERGE`, and an atomic target-plus-outcome DML
   transaction.
3. Select and freeze the affected dbt/dynamic-table closure externally. Invoke
   one multi-table refresh for its selected leaves, then verify the full
   cascaded set at the returned data timestamp.
4. Record the actual dynamic-table refresh action and work statistics; do not
   equate a successful refresh with incremental execution.
5. Keep the authoritative Change Propagation Run and Decision Watermark state
   in the durable application ledger. Snowflake's native histories prove its
   stage outcomes but cannot provide the cross-stage atomic barrier by
   themselves.
