# MDM database tuning for ticket 05b (PostgreSQL 16, schema `mdm`)

Research for [05b](../issues/05b-match-proposal-snapshot-scaling.md). Read-only:
no code, migration or database was touched, and nothing was run against a
database. Written 2026-10-01.

**Source version.** Every repo citation is to `origin/main` at `b3602875`
(PR #771). The local `main` checkout (`66ec4570`) is one commit behind. On
`origin/main`, `002_link_start.sql` replaces `match_proposal_snapshot` and
`merge.py` has changed (811 lines, not 799). Paths below are relative to
`edgar_warehouse/mdm/`. "PG docs" means https://www.postgresql.org/docs/16/.

## The short answer

The slowdown comes from the shape of the queries, not from missing tuning
settings. Five lookups that run on every batch cannot use an index, so each
one reads the whole table:

- two of them combine an indexed condition with an un-indexable one using `OR`;
- one casts the key column before comparing it;
- two compare against jsonb paths that have no index.

The tables grow with every batch, so each batch costs more than the one
before, and a full feed costs quadratic time. That matches the ticket: about
5 minutes per 1,000 Persons at about 7,000 rows, and 150% CPU inside
`match_proposal_snapshot`.

The fix is a small set of indexes, plus rewriting two `OR`s as `UNION`s, so
that each branch is an indexed lookup by key. CLUSTER, partitioning, BRIN,
fillfactor and `plan_cache_mode` do not address this and are not recommended
now (see "What not to do").

PostgreSQL has no maintained cluster key like Snowflake's. `CLUSTER` is a
one-time reorder: "Clustering is a one-time operation: when the table is
subsequently updated, the changes are not clustered", and it holds an
`ACCESS EXCLUSIVE` lock that blocks reads and writes while it runs (PG docs
`sql-cluster.html`). The real equivalents are:

- an index on the lookup key (btree or GIN), which finds the rows wherever they are;
- BRIN, for very large tables whose column values follow physical order (`brin-intro.html`);
- partitioning, for tables larger than memory (`ddl-partitioning.html`).

Only the first fits here.

## How many times each batch scans the store

One `MergeStage.apply` call for a batch with identity work runs these steps
(`clean/merge.py:155-184`):

1. `propose`: bounded lookups through indexes (`binding.py`, `matching.py`). Mostly fine; one exception is finding 5.
2. `assess` → `_execute(preview=True)`. This step runs:
   - `load_closure` (`merge.py:455`), which loops until the key set stops growing (`merge.py:90-122`). That is **at least two** passes, and each pass scans `source_reading` and `decision`.
   - `match_proposal_snapshot`, the first call (`merge.py:479`).
   - `preview_batch`, which runs the whole of `write_batch` and then rolls it back (`merge.py:723`; `001_mdm.sql:870-883`).
   - the retirement query on `current_record` (`merge.py:679-687`).
3. `apply_assessment` → `_execute` again. This step runs:
   - `assessment.check`, the snapshot's second call (`assessment.py:49`);
   - `load_closure` again, at least two more passes;
   - the retirement query again;
   - `save_batch`, which calls the snapshot a **third** time (`001_mdm.sql:550`) before `write_batch`.

So each batch runs about 4 or more full scans of `source_reading` from the
closure, 3 snapshot calls (each scanning four tables), and 2 retirement
scans of `current_record`. Each scan costs time in proportion to the rows
already stored. That is the quadratic total.

## The hot queries and their index support

Existing indexes are listed at `001_mdm.sql:1422-1480`.

| # | Query (where) | Filter columns | Index today | Result |
|---|---|---|---|---|
| A | Snapshot evidence (`002_link_start.sql:22-27`) and closure (`merge.py:94-97`) | `body->>'subject'`, `relationships[*].target_subject / source_subject`, closure also `source_code` | `source_reading_subject` (`001:1438`), `(source_code, mapping_version)` (`001:1422`) | The `OR EXISTS(jsonb_array_elements …)` arm has no index, so the whole `OR` is a **seq scan**. Each row's `body` is read and its relationships unnested. |
| B | Snapshot projections (`002:44-47`) and retirement (`merge.py:681-683`) | `object_type`; relationship `body->>'source_id' / 'target_id'`; review `body->>'entity_id' / 'subject'`, `body->'affected_subjects' ?| keys` | PK `(object_type, object_id)`; partial `current_record_entity_kind` on `body->>'kind'` only (`001:1456`) | None of these body paths has an index, so it is a **seq scan** of every relationship and review row. The ticket says every set-aside record opens a review, so there will be about 45,000. |
| C | Snapshot identities (`002:35-36`) and closure (`merge.py:139`) | `entity_id::text = ANY(keys)` | PK on `entity_id` (uuid, `001:331`) | The cast to text means the uuid index cannot be used, so `master_entity` gets a **seq scan**. It grows by one row per new Person. The schema already fixes this for Company with `company_current_entity_text` (`001:1466`) and `company_alias_current_text` (`001:1460`). |
| D | Snapshot decisions (`002:29-33`) | `decision_id`, `body->>'subject' / 'entity_id' / 'left' / 'right' / 'target'`, and `operation='retire_source' AND body->>'source_code'` | All arms indexed (`001:1442-1450`, PK) **except** `source_code` | One un-indexed arm stops the planner from combining the other indexes with a bitmap OR, so it falls back to a **seq scan** of `decision`, which gets about one bind per Person. |
| D′ | Closure retire query (`merge.py:126`) | `operation='retire_source' AND body->>'source_code'` | none | A **seq scan** of `decision` on every `_execute`. |
| E | Name matching `_stored` (`matching.py:243`, `:256-257`) | `source_code`, `reading->'provenance'->'matching'->'name_census'->'cascade'->>'lei'` | `census_lei`, `lei` and `cik` have expression indexes (`001:1472-1480`); **`cascade_lei` has none** | A seq scan of `stage_record` when the cascade lookup runs, which is a Company/GLEIF path. |
| F | `save_batch` per-row loops (`001:652-694`, `keep_stage` `001:834-866`) | PK / unique lookups | yes | The cost is constant per batch (at most 1,000 rows), **not** growing. A constant factor, not the cause. |
| G | `save_batch` supersede (`001:571-580`), `claim_outbox`, `max(generation)`, `max(published_at)` | `match_proposal_batch` (`001:1430`), `batch_generation_key` (`001:301`), `master_entity_kind_published_at` (`001:1454`) | yes | Fine. |

Why an `OR` with one un-indexable arm reads everything: PostgreSQL can split
an `OR` into separate index scans and combine their bitmaps
(`indexes-bitmap-scans.html`), but only when **every** arm can use an index.
An `EXISTS` over `jsonb_array_elements(...)`, or `body->>'source_code'` with
no index, cannot. So the planner falls back to a sequential scan and checks
the whole condition on every row.

Why the cast matters: an index matches only the expression it was built on.
To search `f(col)` you need an index on `f(col)` (`indexes-expressional.html`),
so a uuid primary key does not serve `entity_id::text`.

## Ranked findings and candidate changes

Each candidate keeps the snapshot hash the same for the same stored state.
Adding an index never changes a result. Rewriting an `OR` as a `UNION`
returns the same set of rows, provided that:

- each branch uses `UNION`, not `UNION ALL`, because one row can match two arms (a review can match on both `subject` and `affected_subjects`);
- each branch keeps its `LIMIT 10001` and the raise when a branch passes 10,000;
- the final `jsonb_agg(... ORDER BY kind, id)` (`002:54`) keeps the hash independent of row order.

All migrations run inside one transaction (`store.py:75`, `:119`), so
`CREATE INDEX CONCURRENTLY`, which "cannot" run in a transaction block, is not
available (`sql-createindex.html`). A plain build locks out writes but not
reads while it runs. At tens of thousands of rows that takes seconds; say so
in the migration.

### 1. Make the `source_reading` evidence lookup indexed (A). Highest value.

- **Helps:** `002_link_start.sql:22-27` and `merge.py:94-97`, about 4–5 scans per batch.
- **Change** (migration 003):
  - Add an IMMUTABLE SQL function `mdm.reading_link_subjects(body jsonb) RETURNS text[]` that returns every `target_subject` and `source_subject` in `body->'relationships'`. It must be IMMUTABLE: "All functions and operators used in an index definition must be 'immutable'" (`sql-createindex.html`). It is a pure jsonb extraction, so it qualifies (`sql-createfunction.html`, volatility definitions).
  - Add a GIN index: `CREATE INDEX source_reading_link_subjects ON mdm.source_reading USING gin (mdm.reading_link_subjects(body))`. The default `array_ops` supports `&&` (overlap) (`gin-builtin-opclasses.html`).
  - Rewrite the query as `SELECT … WHERE body->>'subject' = ANY(keys) UNION SELECT … WHERE mdm.reading_link_subjects(body) && keys`. The closure keeps its third arm, `source_code = ANY(:retiring)`, which `(source_code, mapping_version)` already serves.
- **Deduplicate on the key, not on the whole row:** write it as `WHERE assertion_id IN (SELECT assertion_id … UNION SELECT assertion_id …)` and then read `body`, so the `UNION` compares short ids instead of whole jsonb bodies. The result and the hash are the same.
- **Guard the function:** an index expression runs on every insert. If a stored `body->'relationships'` is ever not an array, `jsonb_array_elements` raises an error, and that error fails `save_batch` itself. Guard it with `jsonb_typeof(...) = 'array'`. Changing the function body later also means a REINDEX.
- **Part of this change is in Python:** the closure query (`merge.py:94-97`) is Python, not migration SQL. The equal-hash test must also check that `load_closure` returns the same `stored_a`, `stored_d` and identities before and after. A different closure gives the snapshot different keys, and the hash then changes for a reason a test of the function alone cannot see.
- **Why not jsonb containment:** a `jsonb_path_ops` GIN on `body->'relationships'` only serves `@>` with one value at a time (`[{"target_subject":"x"}]`). With up to 50,000 keys that means one probe per key. The array-overlap form takes the whole key list in one indexable operator.
- **Expected effect:** each call costs about the number of matching rows, not the table size. While Person readings carry no `relationships` (`rules/sources/sec.submissions.person/source.yaml` has none), the GIN index stays nearly empty and the lookup is the `subject` btree alone.
- **Cost:**
  - one GIN entry per link subject on each insert;
  - `source_reading` is append-only (trigger at `001:1484`), so there are no update costs;
  - GIN's default `fastupdate=on` puts new entries in a pending list until vacuum (`sql-createindex.html`), which is fine here.
- **A limit indexes do not fix:** when GLEIF parent links arrive (06a), one widely linked Company pulls every reading that links to it into each closure (`merge.py:90-122` keeps expanding the key set). That fan-out is logical growth. Watch `len(stored_a)` per batch.

### 2. Index the `current_record` review and relationship lookups (B).

- **Helps:** `002:44-47` (three calls per batch) and `merge.py:681-683` (two calls).
- **Change:**
  - Partial btrees:
    - `(body->>'source_id') WHERE object_type='relationship'`;
    - `(body->>'target_id') WHERE object_type='relationship'`;
    - `(body->>'entity_id') WHERE object_type='review'`;
    - `(body->>'subject') WHERE object_type='review'`.
  - One partial GIN: `USING gin ((body->'affected_subjects')) WHERE object_type='review'`.
  - Rewrite each arm as its own `UNION` branch so that each one is a single indexed lookup.
- **Opclass:** the GIN must use the default `jsonb_ops`. `?|` is supported by `jsonb_ops` but **not** by `jsonb_path_ops` (`gin-builtin-opclasses.html`, `datatype-json.html` §8.14.4). The docs' own example indexes an expression this way: `CREATE INDEX … USING GIN ((jdoc -> 'tags'))` serving `jdoc -> 'tags' ? 'qui'` (`datatype-json.html`).
- **Partial indexes with parameters:** the docs warn that "parameterized query clauses do not work with a partial index" (`indexes-partial.html`). That is about a parameter inside the predicate, such as `x < $1` against `x < 2`. Here the predicate `object_type='review'` is a literal in the query text, so the planner can match it at planning time. Only the key list is a parameter.
- **Expected effect:** each call reads only the matching reviews and relationships, not all of them. The ~45,000 set-aside reviews have no `affected_subjects` (`merge.py:659-677`) and so add nothing to the GIN index.
- **Cost:**
  - **Write amplification.** Every review body carries `affected_subjects`, which is the batch's whole evidence subject set, about 1,000+ entries (`merge.py:643-646`). Each review therefore adds about 1,000 GIN entries, and every upsert of a review (`001:691-692`) and every retirement rewrite adds them again.
  - **No HOT updates.** HOT needs an update that changes no indexed column (`storage-hot.html`). `current_record` already has an expression index on `body` (`001:1456`), so upserts are already non-HOT, and these indexes add entries per update.
  - **TOAST.** These bodies may well be stored out of line, since values over about 2 kB are compressed or moved (`storage-toast.html`).
  - Check first with `SELECT count(*), avg(jsonb_array_length(body->'affected_subjects')), avg(pg_column_size(body)) FROM mdm.current_record WHERE object_type='review' AND body ? 'affected_subjects'` on a populated copy. If the arrays are large, the better fix is in the code: keep `affected_subjects` per review to the subjects that review is actually about. That is a rule and code question for the operator, not physical design.

### 3. Stop casting `master_entity.entity_id` to text (C).

- **Helps:** `002:35-36` and `merge.py:139`.
- **Change**, either:
  - add an expression index `ON mdm.master_entity ((entity_id::text))`, the same pattern as `company_current_entity_text` (`001:1466`), which keeps the queries unchanged; or
  - compare uuid to uuid instead. Note that `merge.py:131-136` already filters `keys` down to valid UUIDs, but the snapshot's `keys` contain non-UUID subjects, so the SQL side would need a safe cast.

  The index is the change that cannot alter the hash.
- **Expected effect:** a seq scan becomes an index lookup, against a table that grows by one row per new entity.
- **Cost:** one small btree entry per insert. The table is append-only (`001:1502`).

### 4. Index the `retire_source` arm of `decision` (D, D′).

- **Helps:** `002:29-33` (three calls per batch) and `merge.py:126` (two calls).
- **Change:** `CREATE INDEX decision_retired_source ON mdm.decision ((body->>'source_code')) WHERE operation='retire_source'`. Once every arm has an index, the planner can combine the existing indexes (`001:1442-1450`, PK) with a bitmap OR. A `UNION` rewrite is optional insurance.
- **Expected effect:** the decision scan stops growing with the number of binds.
- **Cost:** close to nothing. The index only holds `retire_source` rows, which are rare, and `decision` is append-only.

### 5. Add the missing `cascade_lei` expression index on `stage_record` (E).

- **Helps:** `matching.py:256-257` with the lookup at `matching.py:243`.
- **Change:** a btree on that exact expression, `(reading->'provenance'->'matching'->'name_census'->'cascade'->>'lei')`, like `stage_record_census_lei` at `001:1472`.
- **Expected effect:** this is a candidate cause for Company SEC batches going from 33 s to 47 s, because Persons do not run this lookup. Confirm it with `pg_stat_user_tables.seq_scan` on `stage_record` before claiming it.
- **Cost:**
  - **No HOT updates.** `stage_record` is updated by `record_stage` and `record_binding`. Both write columns that are already indexed (`reading`, `entity_id`), so those updates are already non-HOT.
  - **Write amplification.** Each update adds one entry to the new index.

### 6. Statistics and autovacuum: a hypothesis to check, not a finding.

A freshly loaded table can have stale statistics within one long run. Three
things soften this:

- **Batches commit separately, so autoanalyze can run.** Autovacuum analyzes a table once the rows changed since the last ANALYZE pass `50 + 0.1 × reltuples` (`routine-vacuuming.html`, `runtime-config-autovacuum.html`). It checks once a minute (`autovacuum_naptime` = 1 min).
- **The planner scales row counts.** It scales the values it finds in `pg_class` to the current physical table size (`planner-stats.html`).
- **Cached plans are re-planned.** Prepared statements, including the ones PL/pgSQL caches, are re-planned once "their planner statistics have been updated" (`sql-prepare.html`).

The seq-scan shapes above explain the growth on their own, whatever the
statistics say. Expression indexes do get their own statistics, because
"pg_statistic also stores statistical data about the values of index
expressions" (`catalog-pg-statistic.html`), so indexes 1–5 also improve
row estimates. For an expression that needs estimates but no index,
`CREATE STATISTICS` can collect them, "similar to creating an index on the
expression, except that they avoid the overhead of index maintenance"
(`sql-createstatistics.html`). No correlated multi-column filters appear in
these queries, so multivariate statistics have nothing to fix.

- **Check:** `pg_stat_user_tables.last_autoanalyze` against batch times (`monitoring-stats.html`).
- **Lever, only if it lags:** per-table `autovacuum_analyze_scale_factor` / `autovacuum_analyze_threshold` set in a migration (`sql-createtable.html`, storage parameters). The runtime role cannot run ANALYZE itself, because in PG16 that needs the table owner, a superuser, or the database owner (`sql-analyze.html`), and the runtime login holds only SELECT and EXECUTE (`store.py:139-145`).

### 7. PL/pgSQL plan caching.

PL/pgSQL prepares each statement once per session and may cache a generic
plan that does not depend on variable values (`plpgsql-implementation.html`).
The rule is: five custom plans, then a generic plan if its estimated cost is
not much higher (`sql-prepare.html`).

Today this does not matter, because no plan can use an index. After the
indexes are added, a generic plan for `col = ANY($1)` or `&& $1` can still
choose an index scan. Change `plan_cache_mode` only if `auto_explain` shows a
generic seq-scan plan inside the function. If it does, attach
`SET plan_cache_mode = force_custom_plan` to the function itself. A function
`SET` clause applies only while the function runs (`sql-createfunction.html`,
`sql-prepare.html`).

### Noted for the operator, not physical design

The snapshot is computed three times per batch: `merge.py:479`,
`assessment.py:49`, and `001_mdm.sql:550` inside `save_batch`. The second and
third run in the same transaction under the same advisory lock (`merge.py:421`,
`001:535`). Dropping the Python check would save about a third of snapshot
time. But the SQL check is the trust boundary (`SECURITY DEFINER`), so this is
a code-shape change for the GoF consult, not a tuning change.

## What not to do now

- **CLUSTER.** It is a one-time reorder that is not kept up as rows arrive, and it takes an `ACCESS EXCLUSIVE` lock (`sql-cluster.html`). Lookups here go by random subject keys, so physical order does not help them.
- **Partitioning.** It is worthwhile "only when a table would otherwise be very large… the size of the table should exceed the physical memory of the database server". Unique and primary keys must also include the partition key (`ddl-partitioning.html`). The store holds tens of thousands of rows, and `source_reading`'s key is `assertion_id`.
- **BRIN.** It is for "very large tables in which certain columns have some natural correlation with their physical location" (`brin-intro.html`). Subjects do not follow insert order.
- **Covering `INCLUDE` indexes.** The snapshot needs the whole `body`. The docs warn to "be conservative about adding non-key payload columns… especially wide columns", and an index tuple over the size limit makes inserts fail (`indexes-index-only-scans.html`).
- **Fillfactor.** It only helps HOT updates (`sql-createtable.html`, `storage-hot.html`). The large, frequently updated tables all update an indexed column: `current_record.body` (via `001:1456`), `stage_record.reading` / `entity_id`, and `company.valid_to`, which appears in the partial-index predicates `001:1458-1468`. So none of their updates can be HOT, and a lower fillfactor would only waste space. The small tables (`checkpoint`, `outbox`, `run`) update only un-indexed columns (`position`, `fence`, `lease_until`, `report`, `status`), so their updates can already be HOT. They hold a few rows each, so there is nothing to gain from tuning them. The append-only tables should stay at 100, which the docs call "the best choice" for tables that are never updated.
- **Indexes on the `batch_id` foreign keys.** The docs recommend indexing referencing columns because "a DELETE of a row from the referenced table or an UPDATE of a referenced column will require a scan of the referencing table" (`ddl-constraints.html`). `mdm.batch` is never deleted from or updated (trigger at `001:1492`), so these indexes would cost writes and help nothing. No hot query filters by `batch_id`, except `keep_stage`, which joins by `assertion_id` (PK) first (`001:840-841`).

## How to prove it (test plan)

Run only on a **disposable** PostgreSQL 16, never on
`edgartools-clean-mdm-pg16` or `edgartools-change-journal-local-*`.

1. **Baseline on a populated store.** Load the Person proving run
   (`.scratch/onboarding/sec.submissions.person/proving_run.py`) to about
   7,000+ Persons on the current schema, and record per-batch `seconds`.
2. **Count the scans.** Enable `track_functions = 'pl'`. Take `pg_stat_user_tables`
   (`seq_scan`, `seq_tup_read`, `idx_scan`) and `pg_stat_user_functions`
   (`calls`, `total_time`, `self_time`) before and after **one** batch
   (`monitoring-stats.html`). Expected now: `seq_tup_read` on `source_reading`,
   `current_record`, `decision` and `master_entity` of several times each
   table's row count per batch.
3. **See the plans inside the functions.** `EXPLAIN` on
   `SELECT mdm.match_proposal_snapshot(...)` shows only a Result node.
   Use one of two routes:
   - `LOAD 'auto_explain'` (superuser), with `auto_explain.log_nested_statements = on`, `log_analyze = on`, `log_buffers = on` and `log_min_duration = 0` (`auto-explain.html`);
   - or paste the CTE from `002:22-48` out with `keys` bound as a literal array and run `EXPLAIN (ANALYZE, BUFFERS)` (`using-explain.html`).

   Expected now: Seq Scan nodes, "Rows Removed by Filter" close to the table's row count, and mostly shared-buffer hits (CPU-bound, which matches the 150% CPU). Expected after: Bitmap Index Scan or Index Scan on the new indexes, with rows close to the matches.
4. **Hash equality.** For a fixed populated store, call `match_proposal_snapshot`
   on a set of recorded scopes before and after migration 003. Every hash must
   be identical. Also check that `load_closure` returns the same result before
   and after. Add both as tests.
5. **Flat batch time.** Run the 05b target: a 30,000-reading feed with 45,000
   set-aside records. The per-batch `seconds` slope should be about flat, and
   should be reported against the baseline.
6. **Company regression.** Rerun `.scratch/company-mastering/research/27_proving_run.py`.
   Its timings JSON already records per-batch `seconds`. The SEC parts should
   no longer grow from 33 s to 47 s, and the GLEIF batches should not get slower
   from the extra index writes.
7. **Write cost.** Compare `save_batch` total time and index sizes
   (`pg_relation_size`) before and after, especially the review GIN index
   (finding 2).

## Recommendation

**Do first,** as one migration `003` with an equal-hash test:

- finding 1 (`source_reading` link-subject GIN plus the `UNION`);
- finding 3 (`master_entity` text index);
- finding 4 (`decision` retire-source partial index).

These are small, append-only-table indexes with almost no write cost, and
they remove the scans that run most often per batch.

**Next:** finding 2 (`current_record` partial indexes and the
`affected_subjects` GIN). Measure the size of `affected_subjects` first; if
the arrays are large, raise trimming them with the operator, since that
changes behaviour and is not tuning. Finding 5 (`cascade_lei`) is a cheap
add once step 2 of the test plan shows `stage_record` being seq-scanned on
Company runs.

**Do not:** CLUSTER, partition, add BRIN, lower fillfactor, add `INCLUDE`
payloads, index the `batch_id` foreign keys, or change `plan_cache_mode`
without auto_explain evidence. Treat stale statistics as a check to run
(`last_autoanalyze`), not as the cause.
