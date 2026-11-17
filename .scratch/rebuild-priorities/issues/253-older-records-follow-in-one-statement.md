# 253: Older records follow their golden record in one statement, not one a row

Type: bug. Status: resolved (operator, 2026-11-17: consolidate and close; every part ticked, the hosted measurement was taken 2026-11-16 21:02 ET). Blocked by: none. Follows ticket 251.

## Problem

After ticket 251 the hosted GLEIF load merged at 110 golden records a second with 8 workers, against 553 measured for the same batches in rolled-back transactions.

## Root cause (hosted store, 2026-11-16, counts and seconds only)

1. **Why slow?** Every worker's database session was idle, waiting for the client, with the same statement last: the update that points a subject's older records at its golden record. No session waited on a lock, and the workers used no CPU.
2. **Why that statement?** `save_records` sent it through the driver's `executemany`: one statement, one round trip, a row. Proved: 1,000 rows took 58.8 s that way and 0.33 s as one statement, the same rows written (both rolled back).
3. **Why a row for every record?** GLEIF's records were stored before GLEIF could create a Company, each with no golden record. Now each gets one, so every record of a batch has an older row to rewrite. A source loaded for the first time has none, which is why no earlier load showed it.
4. **Why did ticket 251's measurement miss it?** Its batches were timed on records with no older row. The measurement did not cover the case the reload is made of.

## Fix

One update a block of 2,000 rows: each record takes its own golden record through a `case` on its key. Standard SQL, the same on PostgreSQL and MySQL.

## Parts

- [x] 2026-11-16 17:07 ET Test that failed first: `test_a_thousand_older_records_follow_their_golden_records_in_one_statement` (`assert 1000 == 1`: a statement a row).
- [x] 2026-11-16 17:07 ET Proved on the hosted store, rolled back: 58.8 s to 0.33 s for 1,000 rows; the rows written are equal.
- [x] 2026-11-16 21:02 ET Hosted: the GLEIF load restarted on this code. Measured over 182 s of merging with 8 workers: 458 golden records a second (110 before), 33.6 batches a minute.
- [x] 2026-11-16 17:07 ET Learning → skill: `mdm-engineering` "Writes and transactions" (a measurement covers the case the load is made of: records that already have rows, not only new ones).
