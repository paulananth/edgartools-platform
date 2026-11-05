# 194: Production-style run of each source: timings and the optimization plan

Priority: 194. Map: [Rebuild priorities](../map.md). Opened 2026-11-05 02:34 ET (operator, 2026-11-05: "run each source as if we are running in
production measure time and come up with a plan for optimization use locally stored data").

Type: task. Status: in progress. Blocked by: none.

## Question

Run each source whose files are on this machine through the real `load` command into the one local store
(`local-test-server`, rules activated from git), measure the time, and say where it goes.

## Setup (all from git, no test runs)

Rules loaded and approved from `rules/approvals.yaml`, merge rules and 13 sources activated in one pass. Machine: 8 CPUs, 8 GiB;
Docker VM 4 GiB. Counts and times only.

## Measured

| Source | Documents | Bundles | Wall time | Notes |
|---|---|---|---|---|
| sec.company | 76,380 | 150 | 51.6 min (+6.3 min to finish 1 bundle) | 3 bundles at once, 2 workers; 2 database deadlocks, one killed a bundle; 76,352 current records |
| sec.registration (silver) | 732 | 2 | 11.4 min | 732 offerings and 27,415 statement lines landed; found 3 faults (below) |
| sec.submissions.person | 76,380 | 149 | 41.4 min + 57.2 min = 98.6 min | 3 at once: 81 complete, 68 failed at the merge ("Prepared state changed; re-assess"); rerun one at a time, 4 workers |
| sec.nport.registrant | 1 (the quarter's zip) | 1 | 4.6 min | merge 3.9 min of it |
| sec.nport.fund | 1 (the quarter's zip) | 1 | 26.9 min | merge 25.8 min of it (96%) |
| openfigi | 7,714 | 16 | running | first bundle over 30 min |
| sec.nport.security, gleif | 1 each | 1 | not run yet | need a quarter fact; gleif needs two derived files and a publication count |
| sec.company-facts, iapd.adv, sec.ownership, sec.thirteenf.* | not run | | | no captured files in the captures folder (not searched elsewhere) |

### Where `sec.company` spent 240 run-minutes (sum over 151 runs; three ran at once)

combine 68.5 (15 s a run), catalog 65.4 (26 s a run), merge 30.6 (12 s), processed (journal record) 28.4 (11 s), name_count 18.3 (7 s),
records 13.3 (5 s), main (the actual read) 7.0 (1.5 s), keys 3.3. The read is 3% of the run.

## Plan (each item with its evidence; none built yet)

- [ ] The catalog is read again in every bundle (65 of 240 run-minutes, 27%): read a constant input once per run, not once per bundle
- [ ] Every step costs 7 to 26 s whatever its work (claim, report, verify, recheck: ticket 122; PR 1424 fixed the other-run recheck only): measure one tiny step's claim, report and verify separately, then bound them
- [ ] The merge is the long step of the master-record sources (sec.nport.fund 96%, registrant 85%): merge in sets of records, not one by one (ticket 122; the mdm-engineering skill makes the Merge Stage record by record a rule, so it changes only with the operator)
- [ ] Bundles that share keys conflict at the merge (person: 68 of 149 bundles): run such sources one bundle at a time, or make the merge re-assess a stale prepared batch itself instead of failing; say per source which it is
- [ ] Two database deadlocks in claims at 3 bundles at once (sec.company): find the lock order, then retry or fix it
- [ ] The `processed` step (journal record, 11 s) is a write of one row per file set: batch it
- [ ] The load is bound by the database more than by CPU (user time is 2x wall time at 3 bundles): measure the database's share before adding workers

## Where one OpenFIGI bundle goes (553 units, 51,200 records, 52 merge batches; measured 2026-11-05 06:46 ET)

| Step | Seconds | Share |
|---|---|---|
| requests | 782 | 27% |
| the short steps (answers to processed), 1 to 3 chained events each | 370 | 13% |
| **merge** | **1,690** | **58%** |

The merge is 52 batches, one after another, about 30 s each (about 31 ms per record). Each batch is one SQL call
(`mdm_store_apply`), so the database is the cost, not the code around it.

- [x] Cache size is not the cause: 128 MB to 1 GB of cache left a batch at 30 to 33 s (checked on the batch counter and the sampled call lengths, 2026-11-05 06:30 ET). Not shipped.
- [x] Re-parsing is not the main cause: the function parses the 29 MB batch document 109 times, but one parse costs 45 ms (about 3.5 s of the 30 s). Changing it would change a frozen storage protocol (`expected_protocol_fingerprints.json`), so it is not worth it.
- [x] The statements spill to temporary files: the logged plans show `temp read=10158 written=12648` buffers on a statement of 2 s, because `work_mem` is the default 4 MB (`auto_explain` with nested statements, 2026-11-05 06:36 ET).
- [ ] `work_mem` of 256 MB shortens a batch: result in the next line once measured.
- [x] A skill tool measures this, not a hand-written script: `skills/data-operations/scripts/profile_load.py` (`steps`, `sample`), tested on invented values.

## What a first real load of a new source meets (belongs in "Built means ready to turn on")

- [ ] The capture bridge: a source captured by `provider.capture` has no `receipts.jsonl`; the load needs one (written by hand for the registration pages)
- [ ] The silver spec must be registered before landing (`silver register`, by hand today): do it inside the load or the activation
- [ ] The reading's input bound belongs in the reading contract's `execution`, not the source's (PR 1429)
- [ ] The run facts and files each target needs (sec.company: 4 facts and a Name Count) are not named in its rules
- [ ] The migration owner and role names for a store's Rules database are not obvious (the store script knows them)

- [ ] Learning → skill
