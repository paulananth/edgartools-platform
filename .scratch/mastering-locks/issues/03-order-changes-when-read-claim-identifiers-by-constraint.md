# Write each golden record once with its number, and claim identifiers with a constraint, not with locks

Status: resolved
Type: task

The operator asked for a 5-whys and 7-wastes review of the mastering locks during the hosted load of 2026-11-23 ("Why do we need
these locks? Use 5-whys and 7 wastes analysis"). They agreed with it and asked for the design ("Agreed / create correct design").

## Findings (hosted load, 2026-11-23 about 12:00 ET; read-only: statistics and session states, never a row)

- `gleif` mastering ran over 90 minutes on one document. It wrote about 17,000 golden records a minute with 8 workers, while the
  loads used about 1 core of 8. The workers were waiting on the database, not computing.
- `mdm.mastering_master` took 17,089 inserts and 17,605 updates a minute: **every golden record is written twice**. It is
  inserted as pending (`changed_file = 0`), then numbered by `number_changes()` at commit.
- A round trip from the loading machine to the hosted store takes 70 ms. Each merge transaction spends at least three of them on
  locks (`lock_store`, `lock_kind`, `lock_file`), plus one statement of value locks when it gives new identifiers.
- One session waited on the lock manager (`LWLock LockManager`) in the sample. **The share of time spent waiting on the advisory
  locks is not measured** (first part below).

## Measured, part 1 (overturns the lock root cause)

10 minutes, every 10 s, as the reader login, while `gleif` mastered, 464 session samples, about 8 sessions: **advisory `file` lock
1%**, lock manager 0%, any other lock under 1%. The rest: waiting on disk reads (`IO:DataFileRead`) 43%, running 28%, idle in
a transaction while the client computes or sends 23%. A 2-minute sample by statement put the disk reads on the inserts into
`mastering_record`, `mastering_name_key` and `mastering_master` and on their key reads. The store's cache hits 97.8% on a
19 GB database with `shared_buffers` of about 950 MB.

So **the locks are not what limits the load**: the merge waits on the store's disk, then on the client. The 5 whys below
named `lock_file` as the cause; that was read from the code and is wrong for this load. What stands from the review:
every golden record is written twice (17.6k updates against 17.1k inserts a minute), which is disk work on the very tables the
merge waits on, and the extra round trips. Parts 1 to 3 stay, now justified by fewer writes and statements, not by lock
waits. The disk reads are their own question: the next proof reports reads per golden record before and after.

## 5 whys (written before the measurement)

1. A commit takes `lock_file` so that its change number is "highest so far + 1". Without it, a merge that commits late could get
   a number below a reader's checkpoint, and that reader would never see it.
2. The number is given inside the writing transaction: every golden record is written pending, then updated to its number.
3. Three readers resume from a number: the name-search lookups (`lookups.build`), the context's "trust as of file N"
   (`context.py`), and `merge._wake` ("golden records changed since my merge started").
4. None of them runs during a load except `_wake`. The lookups are built only on `--finish --lookups`, and the context search runs
   after the load. `_wake` needs only "changed since I started", not a total order.
5. **Root cause:** the cost of ordering changes sits on the write path, which runs constantly, not on the reader, which runs
   rarely. Similarly, **the database does not enforce one golden record of a kind per identifier value**
   (`mastering_identifier`'s key is `(namespace, value, entity_id)`). Application code enforces it with one advisory lock per
   value. Each advisory lock takes a slot of the shared lock table. That is why a merge may claim at most a fixed number of values
   (ticket 01), and why batches are cut into parts.

## 7 wastes

| Waste | Where it shows |
|---|---|
| Over-processing | Every golden record is written twice: inserted, then updated to number it |
| Over-production | Changes are numbered during the load for readers that run after it |
| Transport | Each lock is a separate statement, at 70 ms from the loading machine |
| Waiting | Every commit of every worker queues on `lock_file`, one transaction at a time |
| Defects | `Contended` and deadlock paths roll a merge back and run it again |
| Inventory | Batches are cut into parts because value locks are limited by the lock table |
| Motion | None found |

## The design

### 1. Each golden record is written once, with its number

Operator, 2026-11-23: "Why do I need a second write it is not one of the 7 wastes". Numbering when read still wrote each row
twice (the pending insert, then the numbering update), so it is over-processing and is dropped.

- **The number is written with the row.** A merge transaction takes its number when it starts, from a counter that needs no
  lock: a PostgreSQL sequence (`nextval`), on MySQL one row of a counter table with `auto_increment`. That is one statement a
  transaction, not one a golden record. The insert or upsert of each golden record writes `changed_file = <its number>`.
  `number_changes()`, `lock_file()`, the pending value 0 and the update all go.
- **What the counter does not give:** commit order. Transaction 7 can commit after transaction 8. A reader that read up to 8
  while 7 was still open would never see 7.
- **So a reader that resumes from a number reads a quiet store.** There are two such readers, and both already run after the
  loads:
  - `lookups.build`, on `--finish --lookups`;
  - the context's `trust`, a report of the last number.

  `lookups.build` refuses while a merge can run: Bookkeeping holds an open run of a mastering target, or another session holds
  a kind lock (`pg_locks`, the kind lock's class; MySQL `IS_USED_LOCK`). Every merge holds its kind lock until it commits, so
  that is exactly "a merge is open", and the caller's own session holds none. It never counts the sessions of a login: the
  build runs under the loader's own login and would refuse itself. `clear` uses the same check (part 3). `--finish` runs after
  every lane is done, so it passes. On a quiet store every number up to the highest is committed, so the order holds without a
  lock.
- **Numbers have gaps, and a record's number can go down.** A merge that rolls back used its number, so a gap is normal and
  never means a lost change. Two merges that change one golden record (the later one waits on its row lock) leave the number of
  whichever commits last, which can be the lower. Neither matters to a reader of a quiet store: it reads every record above its
  checkpoint, and every number taken since its last build is above that checkpoint. A test holds both.
- **`_wake`** today reads golden records changed after `seen`, the highest number when its merge started. With numbers taken
  at start, a merge that started before it and commits after it has a lower number, so `changed_file > seen` would miss it.
  `_wake` reads the holders of the identifiers it waits for whatever their number, minus the ones it wrote. That is a superset of
  today's reading. **Decide by test:** it releases exactly the same records on the concurrent-merge case. If it releases more,
  part 1 stops there and the case goes to the operator as a new decision: no fallback is designed, and none may add a lock or a
  second write.
- **Cost:** one counter statement per transaction, and no update. The proof counts updates of `mastering_master` during the
  merge: zero.

### 2. One golden record of a kind per identifier value is a constraint

- A new table `mastering_claim(kind, namespace, value, entity_id)` with primary key `(kind, namespace, value)`, created by
  `mdm init`. No DDL at run time; this is a schema change for the owner.
- A merge beside others claims its new values with one `insert … on conflict do nothing` (MySQL: `insert ignore`) and reads
  back which claims are its own. A value claimed by another golden record of the kind is the same case as today's `Contended`
  ("an identifier another golden record of this kind holds"): the part merges again, alone. The database's uniqueness replaces
  `lock_values`, so there is **no cap from the lock table**. The cut into parts (ticket 01) then exists only for transaction size.
- A merge alone that combines or splits golden records moves their claims in the same transaction as their identifiers.
- A fresh store gets the table at init. A store that already holds golden records gets its claims filled by `init` from
  `mastering_identifier` joined to each record's kind, before any load. Init only, no migration (operator rule).

### 3. A merge takes no store lock; `clear` refuses while a merge can run

`lock_store` exists only so that `clear` (the whole store) can wait out every merge: each merge takes it shared, which costs one
round trip a transaction, and `clear` takes it exclusive. `clear` never runs during a load, so the exclusion moves to `clear`:
it refuses while Bookkeeping holds an open run of a mastering target, or while another session holds a kind lock (part 1's
check, which never counts the caller's own session). Merges stop taking `lock_store`; `clear` keeps its exclusive store lock for itself.
Of the locks a merge takes today, only `lock_kind` remains: shared beside other merges of its kind, exclusive for what only a merge
alone may do (combine golden records, create by exact name, redo after a deadlock). Without it, two merges could create or combine
one golden record twice.

### What does not change

- A merge of one kind still runs beside the others. Merges that combine golden records still run alone.
- Readers of a quiet store still see every change. `last_file()` is the highest number written, which on a quiet store is the
  highest committed.
- `clear` still clears the whole store, alone.
- MySQL: `GET_LOCK` holds one lock per session, so MySQL merges one kind at a time as now. Part 1 removes its file lock too.

## Parts

- [x] Measure first: lock waits are 1% of merge session time, disk reads 43% (above); the lock root cause is overturned and
  parts 1 to 3 go on for the second write and the round trips (`pg_locks` and `pg_stat_activity` every 10 s for 10
  minutes, reader login) 2026-11-23 13:02 ET
- [x] The design's PostgreSQL behaviour, tested on a disposable PostgreSQL 16 store (6 pass): two open merges take sequence
  numbers without waiting; a rolled-back merge leaves a gap and a quiet reader misses nothing; a record's number can go down and
  a quiet reader still reads it; a reader during merges misses a late commit (why readers need a quiet store); the quiet check
  sees another session's kind lock of the same login and never its own; a claim is won once, the loser waits on the row and
  reads back that it lost, and another kind may hold the value. MySQL is not tested 2026-11-23 13:21 ET
- [x] `/gof-refactor-reviewer` consult: leave the dialect split. `Store` is already a Template Method with `Postgres` and `MySQL`
  hooks, and `store.py` has 3 commits since October. The smallest seam replaces two hooks with two (`lock_file` and `lock_values`
  go; `take_number` with `next_number`, and `quiet`, come in). One open point: the claim table duplicates `mastering_identifier`
  and must follow every identifier writer (`add_identifiers`, `keep_identifiers`, `repoint`, `split`, `clear`); a unique index on
  `(kind, namespace, value)` in `mastering_identifier` itself is simpler if no committed golden records of a kind share a value
  2026-11-23 13:50 ET
- [x] Part 1, each golden record written once with its number: `tests/storage_adapters/test_mastering_write_once.py` (5 tests, each failed first: "a golden record was written a second time", and the missing `take_number`, `quiet`, `NotQuiet`; 5 pass on PostgreSQL and on MySQL); the old test that a reader misses neither merge was rewritten to the quiet-store contract; mastering and context adapter tests 68 pass on each engine. Not built: the Bookkeeping open-run half of the quiet check, and the `lookups.build` guard on a run open between two transactions 2026-11-23 13:50 ET. Tests first, each failing on today's code:
  - a merge writes each changed golden record once, with its number, and takes no numbering lock (today: an insert, then an
    update under `lock_file`);
  - two merges (two connections) take different numbers without waiting on each other;
  - `lookups.build` refuses while another session holds a kind lock or a mastering run is open, runs under the loader's own
    login on a quiet store, and reads every change there;
  - a rolled-back merge leaves a gap and the next build reads every change; two merges of one golden record that commit out of
    order leave the later commit's number, and the next build reads that record;
  - `_wake` releases the same records as today on the concurrent-merge case (decides the open point above)
- [ ] ~~Part 2, the claim table~~ deferred, not built: the measurement (1% lock waits) leaves it no measured gain. It replaces one lock
  statement with one insert statement, so it saves no round trip, and it must follow every identifier writer (`add_identifiers`,
  `repoint`, `split`, `keep_identifiers`, `clear`) on two engines, plus an init backfill. Its one benefit is removing the
  2,000-value cap and the cut into parts, which the next load's `mastering_merge_alone` counts can show to matter or not. Build it
  only if they do 2026-11-23 13:58 ET. Tests it would need:
  - two merges claiming one value leave one golden record;
  - a value held by a golden record of another kind is not a conflict;
  - combine and split move the claims;
  - `init` fills claims for a store that already holds golden records;
  - no merge is cut for the lock table's cap
- [x] Part 3, no store lock in a merge: `test_the_whole_store_refuses_while_a_merge_is_in_flight_and_a_merge_takes_no_store_lock` failed first (`assert [()] == []`: the merge took the store lock) and passes on both engines with the mastering, write-once and clear adapter tests; `Store.take_lock()` with no kind raises `NotQuiet` while another session merges, and MySQL's 32 store slots are one lock. Not built: the Bookkeeping open-run half 2026-11-23 13:58 ET. Tests first:
  - a merge takes no store lock (fails today: every merge takes it shared);
  - `clear` refuses while a mastering run is open, and while another session holds a kind lock; it runs on a quiet store under
    its own login;
  - `clear` still clears an idle store
- [x] Proof, writes (local PostgreSQL 16, 4,000 invented companies in 20 batches, the same script on both code versions): updates of
  `mastering_master` 4,000 rows in 20 statements before, 0 after; statements 681 before, 601 after (4 fewer a batch: store lock, file
  lock, number read, update). Time is equal locally (1.9 s and 2.0 s: no network, warm cache), so **the hosted effect on disk
  reads and round trips is not measured** 2026-11-23 13:58 ET
- [x] Bookkeeping open-run half of the quiet check: `mdm build-lookups` and `mdm clear` refuse while Bookkeeping holds a running run of a mastering target (a worker between two merge transactions holds no kind lock, so the lock check alone cannot see a load); `tests/unit/test_mastering_open_runs.py` (3 tests; the lookups test failed first with `assert 0 == 1`: it built anyway); the hosted store holds 0 running runs now 2026-11-23 15:51 ET
- [ ] ~~Proof on the hosted load: rerun `gleif` on a disposable store~~ deferred, not measurable now: the loads are done, a hosted rerun finds every document already loaded, and a disposable store would not carry the hosted 70 ms and disk behaviour. What stands is the local proof above (4,000 master rows updated before, 0 after). **The check for the next hosted mastering load:** `pg_stat_user_tables.n_tup_upd` of `mdm.mastering_master` stays near 0 during the merge, and the sampled share of disk-read waits is compared with 43%. The hosted store now has the counter (`mdm init` run 2026-11-23: `mdm.mastering_number` exists, the runtime role takes a number)
- [x] Skills: `mdm-engineering/SKILL.md` (a golden record is written once with its transaction's number; readers resume from a number on a quiet store; `clear` refuses while a merge is open) in #2064 and #2065; `data-operations/HOSTED-LOADS.md` (the lookups build and `clear` refuse while a mastering run is open: finish or resume the run first) 2026-11-23 15:51 ET
- [x] Learning → skill: `mdm-engineering/SKILL.md` (write once, quiet store), `data-operations/HOSTED-LOADS.md` (readers refuse while a run is open; read lock waits by sampling). A lock root cause read from code was wrong when measured (1% waits): measure before building a fix for a suspected wait 2026-11-23 15:51 ET
