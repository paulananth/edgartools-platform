# 21: `master_binding` is built inside the database, and only what changed is written

Status: resolved
Type: task

Operator, 2026-11-23, after the hosted `--finish` ran over its five-minute bound: "Is it over processed", then "open the ticket for the
in-database build yes". Ticket 16 decided that a master id is a join inside the data database; ticket 20 made silver find its master
by `silver.master_binding`; this ticket makes the table itself a statement inside that database.

## Findings (hosted `--finish`, 2026-11-23 14:16 ET onward; read-only: statistics and session states, never a row)

- The finish had run 23 minutes when measured, in its last phase: rebuilding `silver.master_binding`, about 4.4 million rows (one per
  source record that has its golden record). It wrote 241,000 rows a minute (4,000 a second) in inserts of 1,000 rows.
- **Per 1,000-row batch the database spent about 16 ms** (3.9 ms on the comparison, 12 ms on the insert) **and the batch cycle took about
  238 ms**: the other 220 ms is the client (two round trips of about 70 ms, and building the rows in Python). Sampling the process: 90%
  of samples were waiting on the network (`poll`). The 220 ms is the remainder, not a direct measurement.
- `links.py` reads every `(source_code, source_key, kind, master_id)` row out of `mdm` into Python (`Store.bindings()`, a join of
  `mastering_record` and `mastering_master`) and writes it back to `silver` through the writer. Both are schemas of one database.
- The writer sent one `SELECT … IS DISTINCT FROM` before each insert (2,414 comparisons, 2,413 inserts) into a table that was empty.
- The table is rebuilt whole on every finish. A daily run that loads a few thousand records would still read and compare all of them
  (read from the code, not measured).

## 7 wastes

| Waste | Where it shows |
|---|---|
| Transport | Every binding goes database → client → database, in 1,000-row batches, at 70 ms a round trip |
| Motion | The same join result is carried by hand between two schemas of one database |
| Over-processing | A comparison before each insert into an empty table; all 4.4 million rows compared again on a rerun |
| Over-production | The whole table is rebuilt each finish for a daily change of a few thousand records |
| Inventory | The table repeats what `mastering_record` and `mastering_master` hold (it is a table only because the mirror carries tables, not views) |
| Waiting | The finish is the last step before Gold and the mirror: 28 minutes against a bound of five |
| Defects | None found |

## The design

- **One statement per direction, inside the database.** The finish runs, as one login that can read `mdm` and write `silver`:
  - `insert into silver.master_binding(source_code, source_key, kind, master_id) select distinct on (r.source_code, r.source_key) … from
    mdm.mastering_record r join mdm.mastering_master m on m.entity_id = r.entity_id order by r.source_code, r.source_key, r.entity_id
    on conflict (source_code, source_key) do update set kind = excluded.kind, master_id = excluded.master_id where
    (master_binding.kind, master_binding.master_id) is distinct from (excluded.kind, excluded.master_id)`
  - `delete from silver.master_binding b where not exists (select 1 from mdm.mastering_record r join mdm.mastering_master m on
    m.entity_id = r.entity_id where r.source_code = b.source_code and r.source_key = b.source_key)`
  
  A first build inserts every row once with no comparison read and no client row. A rerun writes only a changed or new row and deletes
  a row whose record is gone; an unchanged row costs a server-side comparison and no write. `distinct on` keeps one row per key if
  two records ever share a key (the old `select distinct` could return two rows for one key and the writer's key would refuse).
- **It stays a table**, since the mirror carries tables, not views (`sources/managed-mirror.yaml`).
- **Grants:** the login that runs the finish needs `select` on `mdm.mastering_record` and `mdm.mastering_master` and `insert, update,
  delete` on `silver.master_binding`. `init` grants it (no DDL at run time); `harden-hosted-roles.py` and its test say who holds it.
- **MySQL** keeps the writer path for this table (the two schemas are two databases there and the reference storage tests use it); the
  dialect decides, and the PostgreSQL path is the hosted one.
- `silver links` keeps building `relationship`, `relationship_evidence` and `relationship_path` through the writer; they are about 0.6
  million rows against 4.4 million. **Time each phase of the finish first** (below) before changing them.

## Parts

- [x] Timed each phase of `silver links` on the hosted store (three runs, seconds; `Store.rows` is every database read the links make):

  | Phase | Before (the finish, 2026-11-23) | After binding in the database | After one statement per landing batch |
  |---|---|---|---|
  | `calculate`: read `linked_records` | 75 | 76 | 70 |
  | `calculate`: `store.bound` | 138 | 138 | 137 |
  | `calculate`: `store.master_states` | 100 | 100 | 100 |
  | `calculate`: `current_claims`, `project` | 77 | 61 | 62 |
  | `calculate` total | 375 | 402 | 376 |
  | Landing the three relationship tables | 189 | 150 | 90 |
  | `master_binding` | about 1,080 (18 min, through the client) | 99 | 105 |
  | `silver links` | 1,776 (29.6 min) | 661 | 581 (9.7 min) |

  `calculate` is 65% of what remains and 71% of it is database reads (`bound` and `master_states` are 2,000-id `IN` lookups at 300 to 630 ms each: disk reads on the hosted store, not network). The binding run twice at 52 s and 99 to 105 s, the second time with the mirror replicating 2026-11-23 16:15 ET
- [x] Tests first (`tests/storage_adapters/test_master_binding_in_database.py`, 6 tests; each failed first with `AttributeError: no attribute 'bind'`, and the unchanged-rerun test and the gone-record test also fail when the `where … is distinct from` comparison is removed; 6 pass, and the mastering, context and binding adapter tests pass on PostgreSQL and MySQL) 2026-11-23 15:03 ET. Invented records:
  - the in-database build gives exactly the rows `Store.bindings()` gives today (equality, then change the build once to see it fail);
  - the client reads no binding row: no `select` over `mastering_record` runs in Python, and the writer receives no `master_binding` rows;
  - an unchanged rerun writes no row (updated and inserted counts both zero);
  - a record whose master merged into a survivor is bound to the survivor, and a record no longer in MDM loses its binding;
  - two records with one source key leave one row;
  - the finish login without `select` on `mdm` is refused with a message naming the missing grant
- [x] Built: `links.bind(silver)` in `mastering/links.py` (PostgreSQL: the two statements, inside one transaction under the table's lock, an empty result refused as an empty snapshot is, a missing grant named); `links.build` calls it on PostgreSQL and keeps the writer for MySQL 2026-11-23 15:03 ET
- [x] Grants: none to add. The finish login already reads `mdm` (it merges there) and inserts, updates and deletes `silver.master_binding` (the writer does); the hosted run below used it unchanged, and a test names the grants when `select` on `mdm.mastering_record` is revoked 2026-11-23 15:03 ET
- [x] Proved on the hosted store: the rows equal the old build's (an unchanged rerun compared 4,166,083 bindings with 0 inserted, 0 changed, 0 deleted); `silver links` 1,776 s before, 581 s after (the table above). **The finish is still over its 5-minute bound** (9.7 min); the first build into an empty table is not measured. The remainder is `calculate`, which recomputes every link from every record on every finish: deferred to ticket 22 2026-11-23 16:16 ET
- [x] `mdm-engineering/MASTERING-STANDARD.md` (the binding is built by statements in the data database, writing only what changed) and `data-operations/HOSTED-LOADS.md` ("The finish takes at most five minutes": the binding rebuild through the client; one statement a landing batch) 2026-11-23 16:16 ET
- [x] Found while building: the silver writer's PostgreSQL landing made three round trips a batch (insert the missing, find the differing, and for a snapshot read back the keys it had just sent), 70 ms each. It is now one statement a batch for new and unchanged rows (the finding is read again only when fewer rows were inserted than were absent, so an append still refuses a different value another delivery wrote first: `test_the_same_key_delivered_at_once…`), and a snapshot's delivered keys come from the batch when its key columns are text or whole numbers. `test_a_delivery_costs_one_statement_a_batch…` failed first (6 and 9 statements for 3 batches); 77 integration tests that land silver pass 2026-11-23 16:16 ET
- [x] Learning → skill: `mdm-engineering/MASTERING-STANDARD.md`, `data-operations/HOSTED-LOADS.md` (a table moved between two schemas of one database through the client is the defect; count round trips a batch before tuning the batch size) 2026-11-23 16:16 ET
