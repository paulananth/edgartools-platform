# 197: The complete load without the seven wastes, and a merge in milliseconds

Priority: 197. Map: [Rebuild priorities](../map.md). Opened 2026-11-05 21:44 ET (operator, 2026-11-05: "make the merge happen
within milliseconds", then "optimize using 7 wastes the complete job").

Type: task. Status: open. Blocked by: none. Reverses the operator's "accept 60 s a batch" recorded in tickets 194 and 196: the six
plan items of ticket 194 deferred on that ruling are live again and are listed here.

## Question

Which work in a load adds no value, measured, and what does a merge cost once it is gone?

"Milliseconds" is read as per record, with the batch time beside it: a batch is 1,000 records in one transaction, so one batch is
seconds even at 3 ms a record. The floor on this machine is measured below rather than assumed.

## Method

- Every number comes from `mdm_bench`, a copy of the MDM database in the same server (`CREATE DATABASE ... TEMPLATE`, 144 s), with
  no load running. A protocol change is an experimental migration, so it stays off the shared store until it is proved.
- A benchmark batch is one real batch of 1,000 OpenFIGI records with new identifiers, so it makes 1,000 new masters: 3,000 evidence
  entries, 1,000 objects, about 10,000 lookup entries, a 48 MB batch document. The copy of the records stays on this machine.

## Measured

| Step | Batch | Apply call | Other database | Python |
|---|---|---|---|---|
| Baseline, protocol 6 (2 runs) | 57.4 to 65.4 s | 41.7 to 45.4 s | 5.1 to 6.5 s | 10.6 to 13.5 s |
| The routine parses its input once, protocol 7, by the real migration (5 runs) | median 33.3 s (24.0 to 38.4) | median 15.4 s (9.1 to 20.0) | median 7.1 s | median 10.7 s |

## Corrections to earlier findings

- Ticket 194 said re-parsing was not the main cause, from one parse costing 45 ms on a 29 MB document. That figure was about 8
  times too low: a parse of the 48 MB document is about 110 ms, and the routine does it 109 times. Parsing was three quarters of
  the call.
- Tickets 194 and 196 blamed reading pages of a table larger than memory. Across a whole call, reads took 1.8 s and writes 0.3 s
  (`track_io_timing`). The page-read theory is wrong for the apply call.

## Checklist

- [x] Stop the reload to measure alone: bundle 11's batches were all `changed=0`, so nothing was lost; it resumes (2026-11-05 21:24 ET).
- [x] Baseline of one new-master batch on a quiet copy (table above, 2026-11-05 21:37 ET).
- [x] The routine parses its input once: protocol 7 (`SQL.json`); the frozen fingerprints of protocols 1 to 6 are unchanged and the real migration upgraded the copy from 6 to 7 with its data in place (5 runs, table above; storage tests 80 passed, one expectation updated, 2026-11-05 21:56 ET).
- [ ] Prototype the operator's three operations on the copy (operator, 2026-11-05: "looks to me there are too many operation 1) extract 2) load batch to merge stage 3) merge create id"): bulk load to a stage table, then one set-based merge that makes the IDs. This replaces most of the parts below if it holds.
- [ ] Don't store or compare the batch document more times than recovery needs (batch, proposal, three consumers).
- [ ] Python preparation: the batch document is built and hashed more than once.
- [ ] The other 180 statements, 6.9 s: what each read is for.
- [ ] Measure the floor: the same rows inserted with nothing around them.
- [ ] The merge rate of a resumed run: a retained batch costs 2.6 s to step over.
- [ ] Why bundle 11 was loaded again though its records were stored (45 batches of `changed=0`, about 20 s each).
- [ ] Ticket 194's plan, live again: the catalog read in every bundle (27% of `sec.company` run time).
- [ ] Ticket 194's plan, live again: the 7 to 26 s every step costs whatever its work.
- [ ] Ticket 194's plan, live again: bundles that share keys conflict at the merge (68 of 149 for `sec.submissions.person`).
- [ ] Ticket 194's plan, live again: two database deadlocks in claims at 3 bundles at once.
- [ ] Ticket 194's plan, live again: the `processed` step, 11 s for one row per file set.
- [ ] Migrate `local-test-server` to the new protocol and resume ticket 153's reload.
- [x] Learning → skill, part 1: `mdm-engineering` `references/storage-adapters.md`: a generated routine parses its wire once.
- [ ] Learning → skill, the rest.
