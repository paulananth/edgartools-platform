# 233: Batches of one kind merge in parallel

Type: task. Status: resolved (built 2026-11-16, see "Built"; the hosted measurements are taken in ticket 238's load). Blocked by: none. Follows ticket 197's open part
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

## Stopped

Stopped before any code (operator, 2026-11-13: "stop here"), for two findings made while starting the build:

- **Slot locks do not work at this batch size.** A batch holds up to 1,000 records with several keys each, so a few
  thousand keys hashed into a few hundred slots put every batch on nearly every slot: the merge is serial again.
  A lock per key instead would exceed PostgreSQL's shared lock table.
- **What would work is larger.** A coordinator holds the kind lock for the unit, groups batches whose key closures
  (identifiers, name keys, subjects, waiting records, and the identifiers of the golden records they reach) overlap,
  and deals the groups to processes that merge without the lock, behind a fence that sends any batch reading outside
  its closure to a serial pass. That is days of work with a duplicate-golden-record risk on any missed lookup path.
- **The need went away for now.** The hosted GLEIF merge finished at 21:16 ET (6,311 batches, 3,043,084 records,
  partly from earlier attempts the Change Journal skipped). Daily loads merge only changed records, a few minutes
  one at a time. Building now would be over-processing.

Reopen when a daily merge or a full reload is measured waiting on the kind lock. The first step then is cheap: compute
the batch groups read-only for a real manifest and stop if most batches land in one group.

## Measured again (operator, 2026-11-15: "Start ticket 233")

The reopen condition ("a full reload measured waiting on the kind lock") was met by the hosted fresh load: SEC persons, 149
bundles, about 2.8 hours at 1.3 minutes a bundle. Its first step, measuring before building, shows the lock is not what limits it:

- **The lock is held briefly.** 40 read-only samples 1.5 s apart on the hosted store: a kind lock was held in 72% of them
  (every kind counted), the holder's transaction was a median 0.1 s old (at most 2.9 s), and on average 0.1 sessions waited
  for one (at most 1). A persons merge is short; parallel merges would not shorten the load. (The 6.4 of 8 waiting seen with
  GLEIF came from many long merges at once, a different case, and stays the one this ticket is for.)
- **The time is round trips.** One persons bundle of 512 documents takes 110 s hosted (prepare 9 s, merge 62 s, the
  Change Journal's `processed` 38 s) and 8 to 14 s on a local store (2, 5 to 9, 2 to 3 s). A local statement log of 4 bundles
  holds 10,985 statements, about 2,750 a bundle; at the hosted store's 43 ms a statement that is 118 s, the bundle's time.
  Of the 2,750: 512 are `journal.record_event`, one call a file; about 260 are liveness checks (`SELECT 1`, each with its
  own BEGIN and ROLLBACK, from `pool_pre_ping`) on each checkout; about 36 are new sessions, each with about 7 setup
  statements. The merge's own statements are about 100.
- **Decision:** ticket 239 takes the round trips. This ticket's design (key closures, a coordinator) stays deferred until a
  merge of one kind is measured waiting on the lock for long merges: GLEIF, whose merge is measured when it loads.

## Built (operator, 2026-11-16: "implement and fix ticket 233", "there is no need for lock", then "Database guards (Recommended)", and "dont add more tables")

The kind lock is not removed alone: without it, two merges each create a golden record for one identifier (the two-writer
test, 200 of 200). Nor can the store refuse a second holder of an identifier: on the hosted store 365 tickers, 258 LEIs
(16 within one kind), 13 SEDOLs, one CIK and one LoanX value are each held by two golden records, so a unique index would
refuse what the rules allow. What was built instead, with no new table:

1. **Side by side first.** A merge of new records takes its kind's lock shared (PostgreSQL), so merges of one kind run
   together. A merge that creates or merges golden records, joins by exact name, or meets a deadlock is rolled back and
   merged again holding the lock alone, exactly as before. MySQL merges one kind at a time.
2. **Golden record locks.** Beside others, a merge locks the golden records it rewrites (sorted) before it reads their
   members, and before the held-LEI test of a name rule, so two merges that join one golden record read each other in turn.
3. **Identifier claims.** The identifier values a merge gives a golden record that does not hold them yet are locked, then
   read again: one that another golden record of the kind took meanwhile sends the merge to merge alone (at most 2,000
   values a merge; more merge alone).
4. **No lost wait.** After its commit, a merge looks once for a record it left waiting whose identifier another merge gave
   meanwhile, and for one another merge left waiting for what it gave, and merges only those again, alone.

GLEIF finds Companies and never creates one, so its batches merge side by side.

## Parts

- [x] 2026-11-13 21:27 ET Evidence: the kind lock serializes the hosted GLEIF merge (77 of 96 worker samples waiting), and the
      tables alone do not replace it (two-writer test without the lock: 3 of 3 failed, `assert 200 == 0`).
- [x] 2026-11-15 Measured again on the hosted fresh load (persons): the lock is held a median 0.1 s and almost never waited
      for; a bundle's time is its statements times the round trip (110 s measured, 118 s from 2,750 statements at 43 ms).
      The fix is ticket 239; GLEIF is the case left for this ticket.
- [ ] ~~Failing tests, slot locks, golden record locks, components at preparation, measurement~~ deferred until a
      merge is measured waiting on the kind lock: slot locks saturate at 1,000-record batches, and the grouping
      design is not worth building while daily merges are small (see "Stopped").
- [x] 2026-11-16 08:03 ET Merges of one kind that only join stored golden records run side by side; the rest merge alone (Built, above).
      Tests `test_a_merge_that_only_joins_golden_records_runs_beside_another_of_its_kind` and
      `test_a_record_left_waiting_beside_a_merge_that_gives_its_identifier_is_released` failed before (`TimeoutError`: the
      second merge waited on the kind lock); `test_merges_beside_each_other_that_join_one_golden_record_keep_every_record`
      and `test_a_merge_that_creates_a_golden_record_waits_for_one_in_flight_of_its_kind` guard the rest. All mastering
      adapter tests pass on PostgreSQL (39, the concurrency ones five times) and MySQL; 219 mdm, unit and architecture tests.
- [ ] ~~Hosted: the next GLEIF merge, sampled in its first minutes (merge sessions waiting on a lock, records a minute
      against 2,060). The 2026-11-16 resume finished in 18.9 min on batches earlier attempts had merged, so it measured nothing.~~ deferred to 238: the hosted run is done separately (operator, 2026-11-17 06:13 ET: "hosted run will be done seperately").
- [ ] ~~Hosted: GLEIF companies and N-PORT securities merging at once, records a minute each against 6,500 alone and 3,100
      together (moved from ticket 197). Take it at the next load where two kinds overlap; a full-size load is not run only for it.~~ deferred to 238: the same hosted run.
- [x] Learning → skill: data-operations RUNBOOK, "Resource sizing": a hosted store's time is statements times the round trip;
      count a bundle's statements on a local store with statement logging before blaming a lock or adding parallelism. mdm-engineering "Writes and transactions": a merge of one kind runs beside the others and merges alone
      only for what needs it (creating or merging golden records, a contended identifier, a deadlock); a lock per key stays bounded (claims capped).
