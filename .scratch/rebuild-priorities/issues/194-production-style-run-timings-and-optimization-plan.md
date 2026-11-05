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
- [x] Compression of the 26 MB batch value is not the cause: 105 ms (default), 20 ms (lz4), 43 ms (uncompressed) (2026-11-05 06:50 ET).
- [x] **Root cause (measured 2026-11-05 06:58 ET): every batch probes the 6.2-million-row lookup table (4.3 GB, plus a 1.3 GB index) at random places, and the table is larger than the memory the database has.** A batch holds about 19,000 lookup entries; the function probes them in four statements (the stale-version check, the delete, the update, the insert). Joining 19,000 real keys against the table took 24.6 s the first time (disk reads) and 1.6 s the second (in memory). Lookup keys are SHA-256 hashes, so a batch touches pages all over the table and nothing is kept near the previous batch. The Docker VM has 4 GiB for every container; `shared_buffers` (128 MB or 1 GB) did not change the time because the operating system cache is the limit.
- [x] `work_mem` of 256 MB did not give a clean answer: the one-worker run's first call was still running after 170 s (the join test above was confounded by a cold cache). Not shipped as a fix; the PR sets it only as a server default and says so.
- [ ] Decision for the operator (all change a frozen storage protocol, `expected_protocol_fingerprints.json`): (a) fewer or smaller lookup entries per record (19 per record at about 700 bytes today); (b) keys that keep one record's entries near each other, so a batch touches a few pages; (c) a decoded copy of the batch's entries made once, so the four statements stop decoding 19,000 bodies each. Also: the merge fences and records every batch through Bookkeeping, which the operator rules out ("bookkeeping is for resuming a file").
- [x] A skill tool measures this, not a hand-written script: `skills/data-operations/scripts/profile_load.py` (`steps`, `sample`), tested on invented values.

## One-off scripts of this work, and where each belongs (operator, 2026-11-05: "list all one of scripts to tools if needed to the appropriate skills")

Kept outside git in `~/edgar-local-tmp/` and `/tmp`. A tool goes to a skill when a second person or source would need it.

| Script | What it did | Disposition |
|---|---|---|
| `prod-run/sample.sh` | sampled active statements once a second | **Now a skill tool**: `data-operations/scripts/profile_load.py sample` |
| `prod-run/*.start/.end/.log` wrappers | timed one `load` per source, redacted the log | Not needed: `profile_load.py steps` reads the time from Bookkeeping |
| `bench.sql`, `apply.sql` | timed one parse; dumped the apply function | One-off; the method (auto_explain with nested statements) is now one line in the data-operations skill |
| the env-file port edit after a server restart | pointed four env files at the container's new port | **Gap in the skill**: `local-test-stores.py up` refused it from any worktree but the creating one. Fix: `up` rewrites the ports for the owner, or the container keeps a fixed port |
| `t149/gen_contract.py`, `/tmp/gen_silver.py` | wrote the sec.registration rules and Mapping Document from a table of terms | Its output is in git. A generic "contract from a term table" belongs to data-onboarding; not built (one source so far) |
| `t149/read_all.py`, `prove_read.py`, `terms.py`, `runid.py`, `time_frozen.py` | read the pages, counted terms, timed the frozen check | Covered by `source read` and data-profiling; no tool |
| `/tmp/regsilver.py`, `/tmp/silvercount.py` | `silver register` and a row count | `silver register` exists; the count is one query; no tool |
| about 45 other `/tmp/*.py` from tickets 01 to 191 | not read in this work | Not reviewed; one pass over them is a separate task |

- [ ] The server port after a restart: `up` must work for the creating worktree's owner from any checkout, or hold a fixed port (add to ticket 192)
- [ ] Review the 45 older `/tmp` scripts for tools worth a skill

## What a first real load of a new source meets (belongs in "Built means ready to turn on")

- [ ] The capture bridge: a source captured by `provider.capture` has no `receipts.jsonl`; the load needs one (written by hand for the registration pages)
- [ ] The silver spec must be registered before landing (`silver register`, by hand today): do it inside the load or the activation
- [ ] The reading's input bound belongs in the reading contract's `execution`, not the source's (PR 1429)
- [ ] The run facts and files each target needs (sec.company: 4 facts and a Name Count) are not named in its rules
- [ ] The migration owner and role names for a store's Rules database are not obvious (the store script knows them)

- [ ] Learning → skill
