# 233: Batches of one kind merge in parallel

Type: task. Status: open (design written; build not started). Blocked by: none. Follows ticket 197's open part
"narrowing [the kind lock] to the identifiers a batch touches".

## Question

How do batches of one kind (the GLEIF companies) merge side by side, without two golden records for one company and
without a golden record written from stale reads?

## Evidence

- **The kind lock serializes the merge.** On the hosted GLEIF merge with 8 merge processes (2026-11-13, 12 samples
  2.5 s apart, read-only `pg_stat_activity`), 77 of 96 worker samples were waiting on
  `pg_advisory_xact_lock(…, hashtext('company'))`: about 6.4 of 8 workers waiting at any moment. Each process used
  about 6% of a CPU. `merge_file` takes the lock (`mastering/merge.py`, `store.take_lock(settings.kind)`) and holds it
  from the first read to the commit, so `MASTERING_MERGE_PROCESSES` adds no speed for one kind.
- **The tables alone do not protect the merge.** `test_two_writers_on_the_same_identifiers_leave_one_master_each`, run
  on PostgreSQL 16 with `take_lock` made a no-op, failed 3 times in 3 on `assert 200 == 0`: all 200 shared
  identifiers were held by two golden records. The primary keys stop a duplicate row, not two batches each minting an
  id for one identifier (`mastering_identifier`'s key includes `entity_id`).
- **Outside sources** ([research note](../../merge-concurrency-research-20261113.md)): partition the input so tasks
  share nothing; connected components are the blocks; never process one entity id in two writers at once (Senzing);
  a block grows as data arrives; PostgreSQL advisory locks share one lock table, so bound their count.

## Design

1. **Components at preparation.** `mdm.prepare` cuts a unit's rows into batches by connected component: two rows
   sharing an identifier value or a name key go to the same batch (union-find over the rows' keys, then batches
   packed from whole components up to the byte budget). Two batches of one unit then share no key.
2. **Slot locks at merge, in place of the kind lock.** A merge locks hashed slots, in sorted order, before any read:
   one per identifier value, name key and subject of its batch. Batches from other units (another source of the same
   kind, a steward's resolve) take the same slots, so a key two batches share is merged in turn. The slot count is
   fixed (a few hundred), so the lock table stays bounded.
3. **Golden record locks.** A stored golden record can join two components (it holds identifier A and B; one batch
   brings A, another B). After its lookups the merge locks the slot of every golden record it will write, in sorted
   order, then repeats the lookups; if the set grew it locks the new ones and repeats again. A deadlock between two
   merges rolls one back and it retries.
4. **Unchanged.** The store-wide lock `clear` takes, the file number given at commit, and the MySQL path (its
   `get_lock` slots back the same slot numbers).

## Parts

- [ ] Failing test: two concurrent merges of one kind sharing a stored golden record through different identifiers
      leave one golden record holding both records (fails with the kind lock removed).
- [ ] Failing test: two concurrent merges sharing a new identifier leave one golden record (the existing two-writer
      test, run without the kind lock).
- [ ] Slot locks replace the kind lock in `merge_file`, `split_merge` and the steward's resolve.
- [ ] Golden record locks with the repeated lookup and a deadlock retry.
- [ ] Components at preparation (`mdm.prepare` batches).
- [ ] Measure 8 processes on a 1,000-record local slice, then on the hosted GLEIF merge, against the 77 of 96 waiting.
- [ ] Learning → skill: `mdm-engineering`, "Writes and transactions": the merge's unit of exclusion is the key and the
      golden record, not the kind.
