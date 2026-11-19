# Silver deliveries into one table do not wait on each other

Status: open
Type: task
Owner: Claude

Operator, 2026-11-18: "fix The silver table lock still slows ipo and company-facts".

## Findings

- A PostgreSQL silver delivery stages its rows in a table of its own session, then locks the target table in
  SHARE ROW EXCLUSIVE mode and holds the lock through the whole merge (the duplicate check, the changed-row check,
  the insert, the updates and, for a snapshot, the delete). That mode conflicts with itself, so a table takes one
  delivery at a time, whatever keys the deliveries hold. `ipo` runs four bundles and `company-facts` several
  deliveries into one table each, so their bundles queue on the lock and `--bundles` gives no parallelism.
- The table has its key as a primary key, so the database can already refuse or serialise two deliveries of the same
  key by row: the table lock is wider than the rule it protects.

## Parts

- [x] Consult the GoF reviewer: conditional. Taken: `ON CONFLICT (<spec key>)` with the key as target (a bare `DO NOTHING` would skip a row that broke another unique rule), the insert in key order, a deadlock or serialization failure refused with "another delivery changed the same rows at once; deliver again". Not taken: splitting `write` into two strategy classes; the change is two guarded lines and two small helpers in the one function, and the MySQL path is untouched 2026-11-18 21:56 ET
- [x] Measure the cost today on a disposable PG16 (four concurrent deliveries of 30,000 disjoint rows into one table, one process): 2.1 s on the old code, 2.4 s on the new, one delivery alone 0.8 s. In one process the Python row staging dominates, so this benchmark cannot show the lock's cost; the real measure is the `ipo` rate below 2026-11-18 21:56 ET
- [x] Failing tests first: `test_deliveries_of_different_keys_merge_while_another_merge_is_open` failed on the old code (`a delivery of other keys waited for another merge on the same table`); three guards that pass on both (a snapshot still takes the whole table, the same key delivered at once leaves one row and an append refuses a different value, the same rows delivered by two deliveries land once) 2026-11-18 21:56 ET
- [x] Build: a PostgreSQL append or upsert delivery merges by row (`INSERT ... ON CONFLICT (key) DO NOTHING` in key order, then the changed-row check); a snapshot and MySQL keep their table lock 2026-11-18 21:56 ET
- [x] Prove: silver writer and link tests on PG16, 15 passed; silver unit tests, 58 passed 2026-11-18 21:56 ET
- [x] Review fixes: a failed delivery's rollback now removes its staging table (dropping it first raised on the aborted transaction and hid the deadlock refusal); the refusal text is `delivery_refusal`, tested for SQLSTATE 40P01 and 40001 as a unit test; the snapshot and append tests poll `pg_stat_activity` for the lock wait instead of sleeping; the concurrent-rows test asserts both deliveries land 2026-11-18 21:59 ET
- [ ] Known and untested: two upserts that change the same rows in opposite orders can deadlock, and one is refused with "deliver again" (the next attempt carries on); no test forces a real deadlock, since which session the database picks as the victim is not controllable
- [ ] Re-measure on a real `ipo` run: bundles a minute against the 1.2 of ticket 08 (the load is stopped; needs the loaders restarted)
- [x] Learning → skill: data-operations "Cuts bundles" says bundles' silver rows merge by key side by side and only a snapshot takes the whole table 2026-11-18 21:56 ET
