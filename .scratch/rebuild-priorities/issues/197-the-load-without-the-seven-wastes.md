# 197: The complete load without the seven wastes, and a merge in milliseconds

Priority: 197. Map: [Rebuild priorities](../map.md). Opened 2026-11-05 21:44 ET (operator, 2026-11-05: "make the merge happen
within milliseconds", then "optimize using 7 wastes the complete job").

Type: task. Status: open (the merge lock, below). Blocked by: none. Reverses the operator's "accept 60 s a batch" recorded in tickets 194 and 196: the six
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

On the real load the gain was smaller. A real batch went from a median of 53.9 s to about 45 s, about 15% (`mdm_store_apply` 27 s to
about 11 s, read statements 9 s to about 13 s, Python 24 s to about 20 s; 150 samples over about 4.5 batches). Reads and Python run
longer on the live load than on the quiet copy (about 7 s and 10 s). The cause of that difference is not known; the three operations
remove that work, so it is not being pursued.

## The operator's design (2026-11-05)

"looks to me there are too many operation 1) extract 2) load batch to merge stage 3) merge create id"; "current mastering is a over
enginiered piece of crap simplifyit"; "mastering should either create new id or merge with an existing id using lookups"; "merge
matching on matching rules should not create new id it should re use already created and matched id"; "make sure you run a complete
entitty and all sources and test it sec, gelief and other sources".

So a merge looks up each record's identifiers: one master found merges into it, none makes one id, and records of one batch that
match each other share one id. Two different masters found goes to a steward and makes no id.

| Three operations, prototype on the copy | Records | Extract | Load | Merge | Batch |
|---|---|---|---|---|---|
| Lookup only, ignored matches inside a batch (invalid for the rule above) | 1,000 new (5 runs) | 625 ms | 90 ms | 1,086 ms | 1.8 s |
| Matches inside a batch share one id, by recursive SQL | 1,000 new (5 runs) | 643 ms | 103 ms | median 3,333 ms | median 4.1 s |
| Same, onto existing ids | 1,000 changed (3 runs) | 615 ms | 103 ms | median 2,435 ms | median 3.1 s |

Comparison with logging off: protocol 7, 3 runs, median 21.1 s (20.8 to 31.6). The prototype leaves out relationships, field winners
across sources, name matching, history and sending changes to silver, so these figures are a floor.

### Grouping by lookups alone, against the masters the engine made

All stored readings, grouped by the matching identifiers of each kind (`cik`; `sec_series_id`, `lei`; `cusip`, `isin`, `figi`):

| Kind | Sources | Masters | Same records in the same master |
|---|---|---|---|
| company | `sec.company`, `sec.nport.registrant` | 8,361 | 8,361 |
| person | `sec.submissions.person` | 31,097 | 31,097 |
| fund_structure | `sec.nport.fund` | 12,937 | 12,937 |
| security | `openfigi` | 374,083 | 374,083 |

580,718 readings, 5 s in plain Python, once the 4 `merge` decisions (all `openfigi-security-figi`) are applied to the engine's side.
This compares membership only, not field values or relationships, and ignores batch order. Not covered yet: `gleif` with the name
rules, `sec.nport.security`; and with no captured files, `sec.ownership`, `sec.thirteenf.*`, `iapd.adv`.

## Company through the three operations (2026-11-06)

Operator, 2026-11-06: "add field winners and name matching to the prototype", "list code current process and 3-step prototype to see how 3 step improves", "make sure when building use 7 wastes guideline".

The prototype replays all 12,077 stored Company records (`sec.company.v1` 6,414, `sec.nport.registrant.v1` 1,947, `gleif.level1.v1` 3,716) in batches of 1,000 on the benchmark database. It writes no field rule of its own: names go through the real `compare_record_pairs`, and masters through the real `prepare_current_records` and `prepare_master_records`, with the store's own policy. Name matching is a lookup, since each SEC record already carries the result of its Name Count pass. It is local scratch, not committed: `~/edgar-local-tmp/company-proto/`.

| Check against the engine's masters | Result |
|---|---|
| Records bound by the engine and missed by the prototype | 0 of 11,547 |
| Name matches with the same rule | 3,186 of 3,186 |
| Masters with the same members | 8,289 of 8,361; the other 72 are masters the engine emptied (ticket 198) |
| Fields the same in value, winner and conflicts | 65,727 of 65,969; the other 242 are in 50 more emptied masters |
| Records bound only by the prototype | 72, all GLEIF, all onto emptied masters |
| Source order reversed | 8,361 of 8,361 groups the same |

| Step | Median ms a record (3 runs) |
|---|---|
| Load to the stage | 0.30 |
| Identifier lookup | 0.05 |
| Name lookup | 0.04, but about 13 s in total in the batches holding GLEIF records |
| Save records | 0.32 |
| Read members | 0.19 |
| Field winners | 0.61 |
| Write masters | 0.29 |
| Whole batch | 2.4 |

The three runs took 83.6, 46.8 and 36.0 s, so 3.0 to 6.9 ms a record, with the machine busy (load average 7 to 8, another session running). These figures omit extract. The first 25.3 s run is void: it missed a holder arriving in the same batch.

Left out, so these times are a lower bound: relationships, history, review records, decision evidence, quarantine, withheld values, steward overrides, merging two masters, search lookups, delivery to silver, restart. Today's merge is about 45 ms a record on OpenFIGI; the engine's Company merge rate alone is not measured (the GLEIF run took 27 min, most of it not split from reading 3.4M records).

## Every kind on both engines (2026-11-06)

The prototype replays every stored record of the sources below. Matching and field winners run in the shared Rust; the database code sits in one small layer with one plain schema per engine, and no merge code differs between them. It stays local scratch, `~/edgar-local-tmp/company-proto/` (`merge3.py`, `store.py`).

| Source | Records | Merge before | After, PostgreSQL | ms a record before | ms a record after |
|---|---|---|---|---|---|
| `openfigi.security.v3` | 722,984 | 783.1 min | 14.9 min | 65 | 1.24 |
| `sec.company.v1` | 6,414 | 30.6 min | 13.9 s | 286 (a) | 2.17 |
| `gleif.level1.v1` | 3,716 | 12.2 min | 5.1 s | 197 | 1.38 |
| `sec.nport.registrant.v1` | 3,894 | 5.3 min | 3.8 s | 82 | 0.98 |
| `sec.nport.fund.v1` | 25,874 | 67.5 min | 15.2 s | 157 | 0.59 |
| `sec.submissions.person.v1` | 31,097 | 98.6 min (b) | 17.0 s | 190 (b) | 0.55 |
| Total | 793,979 | about 16.6 hours | about 15.8 min | | |

"Before" sums Bookkeeping's merge step over each source's complete runs, which can overlap when bundles run at once. (a) It also covers records set aside by classification, which the prototype does not handle. (b) Wall time of the whole run, with retries, since the summed merge step (3,790 min) overlaps. Earlier runs were on protocol 6.

| Kind | Masters | PostgreSQL | MySQL |
|---|---|---|---|
| security | 376,357 | 376,357 same members, 1,502,676 of 1,502,676 fields, 11 of 11 merges | The same |
| company | 8,361 | 67,034 of 67,034 fields, 3,258 of 3,258 name matches | The same |
| person | 31,097 | 31,097 same members, 31,097 of 31,097 fields | Not run |
| fund_structure | 12,937 | 12,937 same members, 12,937 of 12,937 fields | Not run |

| Engine | OpenFIGI | ms a record | First to last quarter of the run | Company | A merge |
|---|---|---|---|---|---|
| PostgreSQL | 895 s | 1.24 | 0.96 to 1.53 | 22.9 s | median 142 ms |
| MySQL | 1,856 s | 2.57 | 1.23 to 3.34 | 48.0 s | median 231 ms |

MySQL's time is mostly writes (masters 632 s, records 383 s), since it loads by multi-row `INSERT` where PostgreSQL has `COPY`. Time grows with the store on both engines, faster on MySQL. A simulated crash resumed to the same 67,034 fields on MySQL too. The prototype also found the engine's erased masters (ticket 198) and two bugs of its own, each caught only by the larger run.

The machine's sleep log shows no sleep during any prototype run, the first `sec.company` and `sec.submissions.person` runs, or the GLEIF run. It slept 101 min across the first OpenFIGI window, so that run's 783.1 min of merge may hold up to 101 min of sleep: 682 to 783 min, or 57 to 65 ms a record, 46 to 52 times the prototype. "All OpenFIGI" here means the 722,984 records stored, without bundle 15.

## Corrections to earlier findings

- Ticket 194 said re-parsing was not the main cause, from one parse costing 45 ms on a 29 MB document. That figure was about 8
  times too low: a parse of the 48 MB document is about 110 ms, and the routine does it 109 times. Parsing was three quarters of
  the call.
- Tickets 194 and 196 blamed reading pages of a table larger than memory. Across a whole call, reads took 1.8 s and writes 0.3 s
  (`track_io_timing`). The page-read theory is wrong for the apply call.

## Checklist

- [x] Stop the reload to measure alone: bundle 11's batches were all `changed=0`, so nothing was lost; it resumes (2026-11-05 21:24 ET).
- [x] Baseline of one new-master batch on a quiet copy (table above, 2026-11-05 21:37 ET).
- [x] The routine parses its input once: protocol 7 (`SQL.json`); the frozen fingerprints of protocols 1 to 6 are unchanged and the real migration upgraded the copy from 6 to 7 with its data in place (5 runs, table above; storage tests 76 passed, one expectation updated, 2026-11-05 21:56 ET).
- [x] Prototype the three operations on the copy; 6 reuse tests on invented records pass (tables above, 2026-11-05 22:01 ET).
- [x] Group all stored readings by lookups alone and compare with the engine: 426,478 of 426,478 masters match (2026-11-05 22:10 ET).
- [x] Company through the three operations with field winners and name matching, compared with the engine: 0 records missed, 3,186 of 3,186 name matches with the same rule, order reversed gives the same groups (2026-11-06 06:52 ET).
- [x] Silver delivery measured with the real `land()` on a disposable copy, 27,415 `registration_statement_line` rows, batches of 1,000, three runs each: today's id lookup 0.25 to 0.27 ms a row, the merge's own lookup 0.20 to 0.21 ms, ids agree on 340 of 340 masters. A writer-only run was no faster (0.26 to 0.42 ms), so the id lookup is not a measurable cost. `sec.company`, `gleif` and `sec.nport.registrant` land no silver. The cost of the step around the writer is not measured (2026-11-06 07:38 ET).
- [x] Merging two masters: the records of all 11 stored merges, 44 records, one per batch: 11 of 11 merged, 11 aliases, 44 of 44 fields and 11 of 11 members equal the engine; order reversed and a second pass give the same groups; with no merge allowed, 11 go to review and none merge. About 1.4 ms a merge, on small tables. Survivors match on 6 of 11; 10 of 11 pairs tie on `published_at`, so the random id decides (2026-11-06 08:04 ET).
- [x] Restart by file: one row in the file's own transaction, 0.77 ms a file; the record-to-master map moved from memory to the store. Three crashes before a commit resumed to 67,034 of 67,034 fields, a crash before any merge resumed to 11 of 11 merges, and all 15 files delivered again left the masters byte for byte the same. The crashes were simulated by stopping before the commit (2026-11-06 08:04 ET).
- [ ] ~~Prototype scope (operator, 2026-11-06: "add only", "relationship is nothing to do with mastering"): history, review records, decision evidence, quarantine, withheld values, steward overrides and search lookups stay out. Merge exclusions and steward reversals are left out with them, so a real build must decide how they fit.~~ deferred to 199: part of the rebuild.
- [ ] ~~Build relationships after mastering, from the list each stored record already carries, so no source is read twice (operator, 2026-11-06: "the only reason relationship was pushed in to mastering to eliminate 7 wastes of reprocessing"; "relationship is once mastering and silver completes or it can happen after mastering along with silver write"). Claude's recommendation: with the silver write, one pass over the changed records.~~ deferred to 199: part of the rebuild.
- [x] Test the prototype with every kind and on MySQL: every Security and Company master equal on both engines, Person and Fund on PostgreSQL (2026-11-06 09:25 ET).
- [x] Operator's decision: rebuild mastering on the three operations, in stages (operator, 2026-11-06 10:18 ET: "yes open the rebuild ticket and start"). Ticket 199.
- [ ] ~~Measure the engine's Company merge rate alone, on the same 12,077 records, on a quiet machine.~~ deferred to 199: part of the rebuild.
- [x] Group inside a batch in Rust at the load step, one pass, in place of the recursive SQL: `group_batch_records`, 6 Rust tests and 1 Python test. Three runs of 14,024 Company records took 28.6, 23.3 and 24.0 s (1.7 to 2.0 ms a record, load average 9 to 26), and all 67,034 fields, 8,361 masters and 3,258 name matches equal the engine (2026-11-06 07:34 ET).
- [ ] ~~Load `sec.nport.security` and `gleif` with the current engine for a true answer, then extend the comparison to them, with the name rules, field values and relationships.~~ deferred to 199: part of the rebuild.
- [ ] ~~Operator's decision: permission to capture `sec.ownership`, `sec.thirteenf.*` and `iapd.adv`; without it their rules stay unproved.~~ deferred to 199: needs the operator's permission for that request, and belongs with the rebuild's source proofs.
- [ ] ~~Rebuild mastering on the three operations; delete what they replace.~~ deferred to 199: part of the rebuild.
- [ ] ~~Don't store or compare the batch document more times than recovery needs (batch, proposal, three consumers).~~ deferred to 199: part of the rebuild.
- [ ] ~~Python preparation: the batch document is built and hashed more than once.~~ deferred to 199: part of the rebuild.
- [ ] ~~The other 180 statements, 6.9 s: what each read is for.~~ deferred to 199: part of the rebuild.
- [ ] ~~Measure the floor: the same rows inserted with nothing around them.~~ deferred to 199: part of the rebuild.
- [ ] ~~The merge rate of a resumed run: a retained batch costs 2.6 s to step over.~~ deferred to 199: part of the rebuild.
- [ ] ~~Why bundle 11 was loaded again though its records were stored (45 batches of `changed=0`, about 20 s each).~~ deferred to 199: part of the rebuild.
- [ ] ~~Ticket 194's plan, live again: the catalog read in every bundle (27% of `sec.company` run time).~~ deferred to 199: part of the rebuild.
- [ ] ~~Ticket 194's plan, live again: the 7 to 26 s every step costs whatever its work.~~ deferred to 199: part of the rebuild.
- [ ] ~~Ticket 194's plan, live again: bundles that share keys conflict at the merge (68 of 149 for `sec.submissions.person`).~~ deferred to 199: part of the rebuild.
- [ ] ~~Ticket 194's plan, live again: two database deadlocks in claims at 3 bundles at once.~~ deferred to 199: part of the rebuild.
- [ ] ~~Ticket 194's plan, live again: the `processed` step, 11 s for one row per file set.~~ deferred to 199: part of the rebuild.
- [x] Migrate `local-test-server` to protocol 7 from `main` and resume ticket 153's reload (migration ledger 7 of 7 complete, 2026-11-05 22:44 ET).
- [x] Learning → skill, part 1: `mdm-engineering` `references/storage-adapters.md`: a generated routine parses its wire once.
- [x] Learning → skill: `mdm-engineering`, "Choose the cheapest proof": a merge prototype is proved on real batch sizes and whole masters (2026-11-06 10:18 ET).

## Merges take turns on one lock (2026-11-13)

Operator, 2026-11-13: "focus on 197 add what we discussed to improve merging to it", and the store-wide merge lock "goes against 7 wastes remove after testing".

**Measured on the hosted store, while GLEIF companies and N-PORT securities merged at once** (counts only):

| Reading | Value |
| --- | --- |
| N-PORT securities merge rate, alone | about 6,500 records a minute |
| The same merge while GLEIF merged | about 3,100 records a minute |
| Samples (of 60, one a second) with a session waiting on the lock | 52 |

**What the lock is.** `Store.take_lock` (`edgar_warehouse/mastering/store.py`) selects the one row `mastering_lock('merge')` `for update`. `merge_file`, `clear` and the steward's resolve and split take it, so every merge of every source and every kind is one writer at a time. A merge waiting for it is the waste of waiting; the lock itself is not the waste if it is the only thing keeping two merges apart.

**Why it cannot simply go.** Two things the lock hides:

1. The merge's working tables `mastering_stage`, `mastering_stage_key` and `mastering_stage_bound` are shared plain tables, emptied with `delete from` at the start of each merge. Two merges at once would empty and fill each other's.
2. A merge numbers its file `max(changed_file) + 1` over `mastering_master`, and silver delivery reads masters by that number as a watermark. Two merges at once would take the same number, or commit out of order and let a delivery pass a change.

**What does not need the lock.** A merge is per kind (`Settings.kind`); `_release_waiting` re-merges only records of its own kind, and a record never joins across kinds. A Company merge and a Security merge touch different golden records. The remaining cross-kind reads (a Security looking up its issuer's identifiers) are reads; a missed identifier makes the Security wait, and the Company's own merge releases it later.

**The change.** (a) The working tables become per-session temporary tables, as the silver writer's staging already is. (b) A file number comes from a sequence the store owns, not from the table's maximum. (c) The lock is taken per kind, in sorted order, by a merge, and for every kind by `clear` and the steward. A merge of two sources of one kind still takes turns. Tested before it is relied on: two concurrent merges of different kinds finish without waiting on each other and give the masters each gives alone; two of one kind give the same masters as one after the other.

**As built (2026-11-13).** Two points differ from the plan above, each for a reason found while building.

1. The file number is given when the transaction commits, under a short lock of its own (the `file` row), not taken from a sequence at the start. A sequence gives a merge its number first; a merge that then commits after a later-numbered one lands below a reader's checkpoint and the reader misses it. A changed golden record is written with number 0 and numbered as the last step before the commit, so numbers follow commit order.
2. A merge shares the store's lock (the `merge` row, `for share`) and takes its kind's own row (`merge:<kind>`, `for update`). `clear` takes the store's row `for update`, so it waits for every merge without having to list the kinds. The steward's resolve and split take their record's kind, as a merge does: they change golden records of that kind only, and they queue fairly behind that kind's merges.

On MySQL the mastering session reads committed rows (`read committed`), as PostgreSQL does, so the number is read after its lock is held.

**Not done by this change.** One kind with several sources (GLEIF and SEC companies) still takes turns on that kind's lock. Narrowing it to the identifiers a batch touches is its own part, after the per-kind step is measured.

- [x] 2026-11-13 11:35 ET Reproduced on local PostgreSQL: with a Company merge open, a Security merge of one record waited the test's full 30 s and never started (it waits as long as the other merge stays open); with the lock per kind it finishes beside it. Verified by the test named in the lock-per-kind part.
- [x] 2026-11-13 11:41 ET Sampled the hosted GLEIF merge for two minutes, alone on the store (`scripts/dev/run_sample.py`): 9,856 records, about 4,900 a minute. Its time by what the session was doing: 16.2% with nothing open and 5.6% after `BEGIN` (the worker's own Python), 14.4% in the query for waiting records that have no lookup key, 10.6% inserting name keys, the rest in reads of under 5% each. The sampler flags the worker's Python as emulated (x86_64 on this machine), so the rate is a local figure only.
- [x] 2026-11-13 11:41 ET The query for waiting records with no lookup key is gone (14.4% of the sampled merge). It ran on every file to serve a store older than the keys; a record that starts to wait gets its keys in the same merge, and the hosted store holds 914,455 waiting records and none without a key. `Store.unindexed_waiting`, its call and its test are deleted. No test failed before: this removes work, and `tests/storage_adapters/test_mastering_released.py` (2 tests) still passes.
- [x] 2026-11-13 08:55 ET Working tables gone, kept in memory (operator, 2026-11-13: "why does this need to be in database why cant you keep it in memory delete all three tables"): `mastering_stage`, `mastering_stage_key` and `mastering_stage_bound` are removed from both schemas and from the store; a file's records stay on the `Store` and its lookups are blocked `in (...)` queries. Verified: `tests/storage_adapters/test_mastering.py::test_a_merge_keeps_its_file_in_memory_and_leaves_no_working_tables` failed on the old code (`assert not {'mastering_stage', 'mastering_stage_bound', 'mastering_stage_key'}`); 53 mastering and steward tests and 61 integration tests pass on PostgreSQL, 31 mastering tests on MySQL.
- [x] 2026-11-13 11:53 ET The three old tables are dropped (operator, 2026-11-13: "drop old tables") on the hosted store and on the three running local stores of this session; each keeps its 13 mastering tables, and the hosted store its 2,225,789 records. The hosted drop waited for the GLEIF merge on the older code to be stopped, since that merge was writing to them (435 rows in use). Verified by a count of the tables after the drop.
- [ ] Stopped local stores, and another runtime's store, keep the three empty tables until they are next reset: nothing reads them.
- [x] 2026-11-13 11:35 ET File number given at commit (see "As built"): no two merges share one, and a reader never passes an uncommitted change. Verified: `tests/storage_adapters/test_mastering.py::test_a_merge_of_another_kind_runs_beside_one_in_flight_and_a_reader_misses_neither` starts a Company merge, commits a Security merge inside it, and a reader at the Security's number (1) then gets the Company's golden record as number 2; PostgreSQL and MySQL.
- [x] 2026-11-13 11:35 ET Lock per kind: `Store.take_lock(kind)`; `clear` takes the whole store, the steward its record's kind (see "As built"). Test one, the test above, failed on the old code with `TimeoutError` (the Security merge waited 30 s for the Company's lock). Test two existed: `test_two_writers_on_the_same_identifiers_leave_one_master_each` (two Company merges at once, one master each). `test_the_whole_store_lock_waits_for_a_merge_in_flight` covers `clear`'s lock. 82 mastering, steward and context tests pass on PostgreSQL and on MySQL, and 81 integration tests on PostgreSQL.
- [ ] Batch the per-record statements of one merge (fewer round trips), measured on the hosted store before and after.
- [ ] Stage a batch before the lock and hold the lock only for the write.
- [ ] Hosted: GLEIF companies and N-PORT securities merging together, records a minute each, against 6,500 and 3,100. Not measured in the 2026-11-13 reload: N-PORT securities' first pass ended before the lock per kind was out, and a full-size load is not run again only to confirm it. Take the figure at the next load where two kinds overlap. Seen on the hosted store so far: the lock rows `file`, `merge` and `merge:security`, each created on first use.
- [x] 2026-11-13 13:48 ET The merge read each source's contract and each kind's settings again for every batch, about 0.45 s of the 1.4 to 2.6 s a batch costs (measured on the hosted store, 3 batches). They are read once a unit now. Test `test_merge_reads_a_sources_contract_once_a_unit` failed before (`_quiet() takes 2 positional arguments but 3 were given`).
- [ ] A restarted merge unit begins at batch 1 and parses every batch it already merged, 1.1 s of a 1.4 s skip (measured: 585 records, 1.13 s of the 1.37 s in `batch_input`); GLEIF has about 1,800 such batches, an hour. No stored key tells a done batch from its input, since a file key is the hash of the normalized records. Recommended: one nullable column on `mastering_file` (hash of the batch input digest, reading version and policy digest) committed with the batch's last kind and read before parsing. It changes the hosted schema, so it waits for the operator's word.
- [ ] Restarting a running load for new code costs its read and prepare again (48 min for GLEIF, 2026-11-13 11:49 to 12:37 ET) plus about 2 s a merged batch; five GLEIF restarts that day are most of its slowdown.
- [ ] A load restarted from newer worker code starts a new run and reads and prepares its file again ("pinned to other worker code"); GLEIF did on 2026-11-13. Decide whether a run should carry on when only code outside its steps changed.
- [ ] Learning → skill: `mdm-engineering`, "Writes and transactions", holds two rules written with the lock per kind (a merge takes its own kind's lock and keeps its file in memory; a file number is given at commit). The ticket stays open for the measured parts above.
