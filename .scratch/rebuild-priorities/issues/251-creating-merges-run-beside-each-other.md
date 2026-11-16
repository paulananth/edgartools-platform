# 251: A merge that creates golden records by identifier runs beside the others of its kind

Type: task. Status: open (the hosted measurement). Blocked by: none. Follows ticket 233 (merges that only join run beside each other) and ticket 249 (GLEIF creates its Company).

## Question

Why did the GLEIF load run at about 20 golden records a second, and why can it not run beside itself?

## Evidence (hosted store, 2026-11-16, counts and seconds only)

- The load (8 processes, one GLEIF bundle) made about 20 golden records a second, 1.3 batches a minute: 45 s a batch. All 7 working merge sessions waited on the kind lock; one held it.
- One batch of 1,000 creating records alone, in a transaction rolled back, takes 7.3 s in 24 statements, 122 records a second. So 38 s of the 45 was waiting, not work.
- Ticket 233 let only a merge that joins stored records run beside others; a merge that creates raised `Contended` and was redone alone, holding the kind lock. Every GLEIF batch creates (ticket 249), so every batch ran its work twice, one at a time.
- Operator, 2026-11-16: "There is no need for lock": the batches of one GLEIF file carry disjoint LEIs.

## Root cause analysis

1. **Why slow?** 8 workers' batches ran one at a time, and each batch did its work twice. Proved: every working session waited on the kind lock, one held it; a batch alone is 7.3 s against 45 s in the load.
2. **Why one at a time?** A merge that creates raised `Contended` and was redone holding the kind lock alone (ticket 233's design: only a merge that joins ran beside others). Proved by reading the code and by the measurement after the change.
3. **Why was creating treated as alone?** The two-writer test showed duplicates without the kind lock (200 of 200), and the claim of identifier values that covers a create was built for joins only. The GLEIF load joined when that was written ("GLEIF only joins", 2026-10-16).
4. **Root cause:** ticket 249 reversed that ruling, so every GLEIF batch now creates, and nothing re-checked ticket 233's assumption (which merges create) against the new ruling. A second cause: ticket 230 sent `--workers` to the merge, so 8 processes met the lock where one had not.
5. **Why not found before the hosted run?** The cheap proof, one batch's statements timed in a rolled-back transaction, then the same batches beside each other, was done after the run started, not before. It took two minutes and showed 7.3 s a batch.

What I got wrong on the way: I first blamed round trips (a creating batch is only 24 statements, about 1.5 s), then the 40-hour estimate, from 20 records a second, took the contention for the work. Not proved: the 45 s against 7.3 s is explained by the lock queue plus the doubled work; the fix gave 4.5 times in a rolled-back test, but the load itself has not run on it. A restart re-reads the 3 million records (about 15 minutes), which is a separate waste.

## Change

A merge beside others may create a golden record by identifier: the identifier values it newly gives are already locked one by one and read again (ticket 233), and another golden record of the kind holding a value sends the merge to join it. `Contended` stays for a merge of two golden records and for an exact-name creation. The store remembers the ids a transaction created (`minted`), so the row locks skip them.

## Parts

- [x] 2026-11-16 16:17 ET Test that failed first: `test_a_merge_that_creates_golden_records_by_identifier_runs_beside_one_in_flight_of_its_kind` (`TimeoutError`: the second merge waited for the first). Guards: `test_four_writers_creating_the_same_identifiers_at_once_leave_one_master_each` (three runs), the existing two-writer test, and all 84 mastering tests on PostgreSQL and 81 on MySQL (3 skipped).
- [x] 2026-11-16 16:17 ET Measured on the hosted store, rolled back: 1 batch 122 records a second; 4 beside each other 309 (2.5 times); 8 beside each other 553 records a second, 1.8 ms a record (4.5 times), none sent to redo. At that rate 2.8 million Companies take about 1.4 hours (the 8 are a measured 14.5 s for 8,000).
- [x] 2026-11-16 16:17 ET Other pipelines: every source that mints by an identifier (SEC filers by CIK, N-PORT and N-CEN registrants, Form ADV by CRD and CIK, persons, funds, Securities by FIGI, CUSIP and ISIN) now merges beside the others of its kind; Form ADV custodians by exact name and the Form 4 issuer-and-symbol Security still run alone. 1,280 mdm, architecture and GLEIF tests, and 42 integration tests (exact-name binding, N-PORT, 13F, N-CEN, Form 4, the company fixture, the declared chain) pass.
- [ ] Hosted: resume the GLEIF load (`--workers 8`) on this code and measure records a second; the merge then ends in about 1.4 hours plus a restart's re-read of about 15 minutes.
- [x] Learning → skill: `mdm-engineering` "Writes and transactions" (a kind lock serializes what a key lock allows; creating by identifier runs beside others), `data-operations` RUNBOOK "Resource sizing" and the alone list (time one batch alone, rolled back, before blaming a lock), and `CONTEXT.md` Merge Stage.
