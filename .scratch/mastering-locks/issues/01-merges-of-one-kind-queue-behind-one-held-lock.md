# Merges of one kind queue behind one exclusive lock held while a worker computes

Status: resolved
Type: task

Operator, 2026-11-18, after the second hosted load showed "database pressed": "Did you find the root cause of the deadlock in the
database", "Yes please" (find the kind, measure the cost), then "Fix it".

## Findings (five whys, measured on the live load through the diagnostic login: statistics and lock tables, never a row)

- There was no deadlock: `deadlocks` read 0 in all six databases and no log held one. There were lock waits: advisory, in `mdm`.
- Every waiter, in 10 of 12 samples, waited on one key: the exclusive lock of the **security** kind (the key's hash matched that
  kind's name). OpenFIGI answers and N-PORT security merge that kind at once, and 13F securities will.
- Of the `mdm` sessions that were active, 84% were waiting on a lock (4.5 of 5.4 on average); 0.7 of about 34 were running anything.
  The database was nearly idle.
- The holder was `idle in transaction`, waiting on the client, in every sample that caught it: its transaction had run a median
  12 s and at most 15 s. The merge held the kind's exclusive lock while a Python worker computed between statements.
- A merge beside others of its kind claims each new identifier value with its own advisory lock, at most 2,000 values a batch (every
  advisory lock takes a slot of the shared lock table). A larger batch "merges alone": the whole piece, exclusive. A fresh load's
  pieces hold far more than that, so nearly every one went exclusive; a daily batch is small and never did.

## Parts

- [x] Cut a batch, before its first attempt, into parts of at most the cap's distinct identifier values; each part is a file and a
  transaction of its own and merges beside the others of its kind (2026-11-18 14:27 ET;
  `test_a_batch_over_the_claim_cap_merges_in_parts_beside_one_in_flight_of_its_kind`: `TimeoutError` waiting for the merge in
  flight; `test_a_batch_with_one_record_that_merges_golden_records_is_split_and_gives_the_same_masters`: `KeyError: 'files'`;
  PostgreSQL adapter tests: 67 passed, unit tests for the worker and receipts: 45 passed)
- [x] The cut is a pure function of the records, so a rerun finds each part's file done and the journal's receipt names the parts
  (2026-11-18 14:27 ET; a pre-code consult found a split decided by which attempt failed would cut a rerun differently; the second test reruns the batch)
- [x] The worker records every part's file (the receipt's check needs each key done) (2026-11-18 14:27 ET; unit tests for the worker, 45 passed)
- [x] Neither changed file is pinned into the processing identity, so no load reprocesses (2026-11-18 14:27 ET; `runtime_files()` read: 42 files, none of the three)
- [ ] ~~Measure the lock wait on a load with the change, and which `Contended` reasons remain~~ deferred to ticket 02
  (`02-the-remaining-reasons-a-merge-goes-alone`): the exact-name join and a merge of golden records still send a part alone
- [x] Learning → skill: mdm-engineering, the merge-locking paragraph (2026-11-18 14:27 ET; the sentence, read in the PR)
