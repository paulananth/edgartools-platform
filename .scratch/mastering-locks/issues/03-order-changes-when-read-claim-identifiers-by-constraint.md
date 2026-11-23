# Order changes when they are read, and claim identifiers with a constraint, not with locks

Status: open
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

### 1. Changes are numbered when they are read, not when they are written

- A merge writes a changed golden record with `changed_file = 0`, which means pending. `master_upsert` already resets the number
  on a real change and leaves an unchanged record alone. `number_changes()` and `lock_file()` leave the merge path, so a merge
  commits with no store-wide wait and no second write.
- **Numbering is a reader's step:** `Store.number_pending()` takes the numbering lock, then runs one set-based statement:
  `update mastering_master set changed_file = <last + 1> where changed_file = 0`, then commits. Two writers call it:
  - `lookups.build`, before it reads, since it resumes from a number;
  - `load_chain.py --finish`, so a finished load leaves nothing pending.

  The context search reads with a read-only login, so it never numbers. Its `trust` reports the last number and whether
  changes are still pending. After `--finish` nothing is pending.
- **Why the order still holds:** the numbering statement sees only committed rows (each statement in PostgreSQL's read-committed
  mode reads what was committed when it started; MySQL InnoDB reads the latest committed version for an `UPDATE`). It gives them
  all number N, under one lock that only numbering takes. A merge that commits later stays pending and gets N+1 or above at the
  next numbering. So a reader that has seen N has seen every change committed before N was given, which is the property
  `number_changes` promised.
- **Cost:** one set-based statement per reading on the server, with no round trip per row and no worker waiting. At `--finish`
  it numbers the whole load once. **It is still a second write of each pending row**, done once in bulk on the server instead of
  once per transaction under a lock, so the claim "no second write" holds only for the merge path. Measure the bulk statement on
  the proof load; if it is too slow, number by kind or in key ranges, still under the one numbering lock.
- **`_wake`** compares golden records changed after `seen` (the last number when its merge started). During a load nothing is
  numbered, so it must also read pending rows: `changed_file > seen or changed_file = 0`. That is a superset of what it reads
  today. **Open, decide by test, not by reading:** whether the superset releases exactly the same records, or wakes more than
  it should. If it differs, `_wake` keeps a start marker of its own (the pending rows it could already see at its start),
  never the store-wide lock.

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
it refuses while Bookkeeping holds an open mastering run, or while any session of the loader login is connected to the data
database (the reader login sees both). Merges stop taking `lock_store`; `clear` keeps its exclusive store lock for itself.
Of the locks a merge takes today, only `lock_kind` remains: shared beside other merges of its kind, exclusive for what only a merge
alone may do (combine golden records, create by exact name, redo after a deadlock). Without it, two merges could create or combine
one golden record twice.

### What does not change

- A merge of one kind still runs beside the others. Merges that combine golden records still run alone.
- Readers still see changes in order. `last_file()` keeps its meaning once numbering has run.
- `clear` still clears the whole store, alone.
- MySQL: `GET_LOCK` holds one lock per session, so MySQL merges one kind at a time as now. Part 1 removes its file lock too.

## Parts

- [x] Measure first: lock waits are 1% of merge session time, disk reads 43% (above); the lock root cause is overturned and
  parts 1 to 3 go on for the second write and the round trips 2026-11-23 13:02 ET. The measurement as planned: sample `pg_locks` (advisory, `granted = false`) and `pg_stat_activity` wait events every 10 s for
  10 minutes during a mastering step, through the diagnostic login. Report the share of merge-transaction time spent waiting on
  each lock key. Go on with part 1 if `lock_file` waits are a material share, or regardless for the second write
  (measured: 17.6k updates against 17.1k inserts a minute)
- [ ] `/gof-refactor-reviewer` consult on `edgar_warehouse/mastering/store.py` and `merge.py` before code
- [ ] Part 1, numbering when read. Tests first, each failing on today's code:
  - a merge's commit takes no numbering lock and writes each changed golden record once;
  - a merge committing after a numbering is numbered at the next numbering, never below the reader's checkpoint
    (two connections, PostgreSQL adapter);
  - `lookups.build` numbers first and reads every change; the context's `trust` names pending changes and writes nothing;
  - `--finish` leaves no pending row;
  - `_wake` releases the same records as today on the concurrent-merge case (decides the open point above)
- [ ] Part 2, the claim table. Tests first:
  - two merges claiming one value leave one golden record;
  - a value held by a golden record of another kind is not a conflict;
  - combine and split move the claims;
  - `init` fills claims for a store that already holds golden records;
  - no merge is cut for the lock table's cap
- [ ] Part 3, no store lock in a merge. Tests first:
  - a merge takes no store lock (fails today: every merge takes it shared);
  - `clear` refuses while a mastering run is open, and while a loader session is connected;
  - `clear` still clears an idle store
- [ ] Proof: rerun the mastering step that limited the measured load (`gleif`) on a disposable store. Report golden records a
  minute and the inserts and updates of `mastering_master`, against 17k a minute and two writes a record
- [ ] Skills: mdm-engineering's lock paragraph (merges no longer number changes; claims are a constraint; the cap is gone);
  data-operations' `--finish` (numbers pending changes)
- [ ] Learning → skill: name the skill lines changed, or "none"
