# 238: A fresh load into the hosted store, initialized again

Type: task. Status: open (the one hosted run: every hosted part of every other ticket is below). Blocked by: none.

## Why

Operator, 2026-11-15: "do not load local-test-server, i need a plan to load fresh copy, re initalised in snowflake
hosted postgress". The rework of every source extract (ticket 235) and the two-path split (ticket 237) changed what
each source's rules are, so every source loads again anyway; the hosted store also holds loads from older code
(2026-11-11 to 2026-11-13) and an unrotated credential set. A fresh store loaded once, in order, from today's code is
simpler than reprocessing on top of it. The operator's rulings that followed the plan: no credential rotation; everything
else is stopped and the work owns the store; delete the old store; "start from runbook the goal is to optimize the
runbook".

## What "fresh" means

- **Emptied:** MDM masters and records, silver, Bookkeeping runs, the Change Journal.
- **Kept:** the rules in git, the RDM code sets (restored from git), the captured files on this machine. No provider
  request: every load reads a capture already here.
- **Initialized again:** the hosted databases, their owners, roles, logins and grants, the schemas, RDM codes and
  source registrations, by the runbook ("Initialize a hosted store", `skills/data-operations/RUNBOOK.md`).

## Gates and decisions (operator, 2026-11-15, one answer to each)

- [ ] ~~Credentials rotated~~ not done: operator, 2026-11-15: "do not rotate credencials". The existing logins and
  passwords carry over; the `mdm_runtime` password reset stays open in the older items.
- [x] No one else uses the hosted store: operator, "you own everything all other are stopped"; read-only check before
  the drop: no other session on the six databases (2026-11-15 13:45 ET)
- [x] The old store's evidence: operator, "delete old store". The six databases were dropped (MDM 18 GB, silver 3.9 GB,
  Change Journal 585 MB, the rest small) and the 114 GB of run artifacts under `hosted-prod/manifests` deleted, with the
  retained load logs of that store (2026-11-15 13:45 ET)
- [ ] Qualification: this fresh load's counts against the local proofs of the same captures are the record the operator
  weighs once the chain is done (below)
- [x] Decision 1: the instance and its logins stay, the databases are made again inside it (so no credential changes)
- [x] Decision 2: no backup (operator, "delete old store")
- [x] Decision 3: the captured cohorts are loaded as they are (ownership 5,356 files, 13F securities 52, 13F filings 10,
  registrations 732, company facts 368); a full-history capture is a provider request and needs its own word
- [ ] Decision 4: GLEIF is the last of the master loads in `rules/load-chain.yaml`, and its first attempt is measured
  (records a minute, the estimate for 3.4 million records); over a day, stop and take ticket 233 first

## Before the reset (local, no hosted write)

- [x] The load order, each target's capture, facts, revision and workers are one file, `rules/load-chain.yaml` (41 steps,
  masters first and each source's silver last); the sequence file stays the offline one-target-a-source inventory
- [x] `load --plan` for every step against the empty hosted store: no step blocked; SEC company 76,231 documents in 150
  bundles, persons 149 bundles, OpenFIGI 7,714 in 16, ownership 5,356 in 11 (2026-11-15 13:45 ET)
- [x] The machine stays awake for the whole chain (`caffeinate` inside `load_chain.py`); 268 GB free after the old
  artifacts went (N-PORT security needs about 32 GB)

## Initialize (hosted; runbook steps 1 to 7)

- [x] The six databases dropped and created again with the owner and grants each had (`reset-hosted-databases.py`;
  grants read before the drop and compared after: identical) 2026-11-15 13:45 ET
- [x] Schemas, each with its owner login: MDM (58 s), the MDM guard, RDM, Bookkeeping, the Change Journal, silver, rules;
  every schema file printed its checksum
- [x] RDM codes: 15 code-set versions restored from git, every pin `pin ok` (81 s)
- [x] Registration login granted (`mdm grant-registration`, 3 s); `rules check` 19 sets ok; `rules register` (17 s)
- [x] Silver: 11 table specs registered (30 s); the ten worker profiles granted (12 s)
- [x] `doctor` ok under `worker.env`; `load --plan` reads a capture. About six minutes of commands in all (2026-11-15 13:45 ET)

## Runbook friction found, and what changed (the goal of this run)

| Found while following the runbook | Waste | Change |
|---|---|---|
| Two folders held the hosted connection files; the one the skill named held logins from before the 2026-11-12 reset, and `doctor` failed under them | Inventory, defects | One folder, `~/.config/edgartools/hosted/`, the live files; `verifier.env` (a duty that no longer exists) and the stale copies gone; skills name the one folder |
| 114 GB of the old store's run artifacts on disk | Inventory | Deleted with the old store; the reset section says the artifacts go with it |
| Step 2 sent the reader to a section with no commands; the only code was inside the local-store script | Motion | `infra/scripts/reset-hosted-databases.py` (lists, refuses while a session is connected, `--confirm`), tested |
| The Change Journal's init refused a fresh hosted database ("must hold only the journal"): the platform puts `extension_base.workers` in every database | Defect | The guard ignores the platform's schemas (PR 1807, with its failing test) |
| Step 3 said `init` then `migrate` for each store: on a fresh store the second prints the same checksums | Over-processing | `init` only; `migrate` for a later schema file; the owner variable each command reads is written out |
| Step 5, the registration login, had no command (the grants lived in `local-test-stores.py`) | Motion | `edgar-warehouse mdm grant-registration --role <login>`; the local script calls the same function |
| The silver table specs were registered by a local-only script | Motion | `deploy-silver.sh` takes an environment name or a connection file |
| Step 7 named the worker grants and the MDM guard and gave no command | Motion | The commands are in the runbook, in one loop |
| The load order and each load's facts lived in uncommitted per-source scripts in the load logs (seven copies of one retry loop) | Motion, over-production | `rules/load-chain.yaml` and `load_chain.py`: `--plan`, `--from`, `--only`, `--finish`; a test ties it to the real targets |
| `doctor` checks four of the six stores | Defect (unproved) | The runbook says which steps prove RDM and silver; extending `doctor` is left |
| The rules skill text still told a reader to provision `rules_governance` and approver roles for an activation that no longer exists | Over-production | The connection section names only the registration login |

Left as found: the three `discovery_reader_*` logins keep the CONNECT grants they had; the code set
`mdm-relationship-types-before-real-names` restored from git names a history the version 1.0 ruling removes (its own
change).

## Dependencies (operator, 2026-11-15: "Infer dependency and document in the run book. This is not depend on machine capacity")

- [x] `infer_dependencies.py` reads the rules (merge rules' `on_no_match` and `holder_source`, contracts' and silver tables'
  link targets, `pieces`, the targets that build the links table) and prints must, prefer, either-order and alone
  (2026-11-15 14:43 ET)
- [x] `rules/load-chain.yaml` follows it: every `waits_for` and lane order is an inferred edge, and tests hold the two equal
  (changing one wait fails the test it should: the last links build must follow every source that states links)
- [x] Found by the inference: the links table is rebuilt whole at each build, so the last build must follow every source
  whose contract states links. My first lanes let GLEIF, the last build, run before ownership; it now waits for ownership
  and Form ADV. A wait I had added by hand (persons before ownership) is not a dependency and is gone; the loads of one kind
  of master data only take turns
- [x] The runbook's "Dependencies between loads" states the rules without a word about capacity; this store's dependencies
  are under its Examples heading (2026-11-15 14:43 ET)

## Load (hosted; `python skills/data-operations/scripts/load_chain.py`)

- [ ] The chain on the re-initialized instance, started 2026-11-18 06:33 ET with the eight lanes (runbook, "Load a fresh store"; no script of its own): 43 steps in `--plan`, none blocked. Found in its first 20 minutes, each fixed in the skill or runbook:
  - [x] Silver loads stopped with "a value is not its column's type": the database said SQLSTATE 42501. The provisioning command revoked PUBLIC and granted only CONNECT, which also took the right to temporary tables the silver writer stages each load in. It now grants CONNECT and TEMPORARY (`test_a_login_may_connect_and_use_temporary_tables_on_its_database` failed first: no `GRANT CONNECT, TEMPORARY`); applied live with the same command, `silver_runtime` TEMP true, `doctor` ok (2026-11-18 07:03 ET)
  - [x] The silver writer's refusal names the SQLSTATE and the constraint or column, never a value (`test_a_refusal_names_the_sqlstate_and_constraint_never_a_value`: ImportError, `refusal` did not exist; the old message carried no SQLSTATE, so its assertion on `SQLSTATE 42501` could not hold) (2026-11-18 07:03 ET)
  - [x] OpenFIGI stopped on "no document of the bundle matches '*company_tickers_exchange*'": its rules read the SEC tickers file beside the answers, in each capture folder, and the folders lacked it (the part moved here from ticket 248). Copied from the SEC Company capture that retained it (sha256 equal to that capture's receipt), with a receipt line, in both OpenFIGI capture folders; no provider request. The runbook now lists it as a **Needs** dependency (2026-11-18 07:03 ET)
  - [x] The runbook leaves the skill: `skills/data-operations/RUNBOOK.md` is now three runbooks, `docs/runbooks/edgar-intelligence/` initialize, daily run and CI/CD (operator: dependencies must be documented in the runbook; the runbook cannot be named for a skill, it takes the product name). Skills name it in words, since an installed skill cannot link outside its folder; the runbook links into the skills (2026-11-18 07:03 ET; portability, role-skill and load-chain tests, 26 passed)
  - [x] The machine (8 cores, 8 GB) overloaded under eight lanes: load average about 16, swap 8.3 of 9.2 GB used. It recovered to about 7 as short lanes finished (2026-11-18 07:50 ET; live read)
  - [x] GLEIF joins only the SEC Company masters yet waited behind N-PORT security in lane L, and N-PORT silver likewise: each now has its own lane (G, N), started at 07:43 and 07:42 ET (`test_the_chain_has_ten_lanes_and_company_facts_is_beside_the_other_silver_only_sources` failed first: the lane set had eight); GLEIF at 8 workers as measured before (2026-11-18 07:50 ET)
  - [x] The chain's state file still held 77 `done` lines of the 2026-11-15 run, so on this store dependencies were satisfied by them (ownership started before the Company load finished): the old lines are archived beside the file; the initialize runbook says a fresh store starts a fresh state file (2026-11-18 07:50 ET; live check: the state file now holds only 2026-11-18 lines, 37 `done` among them, and the lanes went on)
  - [x] The scheduler: `load_chain.py --auto` watches the loads and starts the head step of every lane whose dependencies are done, longest first, while a slot is free and the machine has headroom (operator: "make data operation skill to be intelegent to keep watching the loads and start based on lane avilability"). Tests, each failing before `ready`, `blocked`, `stalled`, `has_headroom` and `auto` existed (AttributeError): lane order and waits, longest first and the slot bound, one load per source and target, a failure blocking through the lane and the waits, the stop when only blocked steps remain, and the loop to the end with fake children (2026-11-18 07:50 ET; 28 tests)
  - [x] Spec review of the scheduler: N-PORT security queued behind four N-CEN fund loads it does not need, so it has its own lane Q (eleven lanes; the N-CEN class step now waits for both N-PORT security steps, which the lane order had given; `test_a_load_follows_the_sources_its_rules_prefer` failed on the missing edge until it did); the scheduler starts first the step whose minutes plus the longest chain behind it is largest (`test_a_short_step_that_gates_a_long_tail_starts_before_a_longer_step_that_gates_nothing`: `chain_length` did not exist); `stalled` was dead code and went, with a test that a failure under low headroom does not stop the scheduler; the chain file and runbook say what the tests hold (2026-11-18 08:01 ET; 39 tests)
  - [x] The scheduler adjusts to compute under a strict deadline and watches the database (operator: "monitor and adjust based on compute with strict deadline", "monitor db load and locking", "database contention must be addressed by architecture and scaling principles"): workers move 2 to 8 by the machine's load and swap and the database's lock waits and connections, longest chain first up and shortest first down; `--hours`/`--deadline` stops every step it started at the deadline and names what is left; a run behind its schedule is allowed twice the cores in load. Tests, each failing before the functions existed (AttributeError): `pressure`, `rescale`, `behind`, `db_level`/`worst`, the deadline stop, a step restarted at 2, 4, 8 workers, and workers falling while the store locks with the machine at `low`. The live read on the re-initialized store: 2 sessions active, 27 of 500 connections, 0 lock waiters, so the squeeze is the 8 GB machine, not the database (2026-11-18 08:12 ET; 38 tests). The daily-run runbook states the contention ladder: measure the tier, fix the hot spot in the design, scale the saturated tier, throttle last
  - [x] Diagnosis reads as a reader login (operator: "data operations should use a reader role for diagnosis"): `ops_reader` has `pg_monitor` and connects to no store; the provisioning command makes it and `reader.env` (`test_the_diagnostic_login_reads_sessions_and_locks_and_connects_to_no_store`, `test_reader_env_is_made_once_private_with_a_new_password_and_moves_with_the_other_urls`: `ensure_reader` did not exist); the scheduler reads the database with it, not the owner (2026-11-18 08:15 ET; live: it reads active 1, connections 25 of 500, lock waiters 0, is a pg_monitor member, and `mdm` and `silver` refuse its connection)
  - [x] Priorities and the projection use the measured time of each step (operator: "using the actual time then optimization, I would like to use at least 250 connection"): `measured`, `estimates`, `remaining` (a step past its estimate counts its bound, so the figure is an upper bound), `room` and `--connections 250` (`AttributeError` before each existed). Live: 31 of 43 steps done; the done steps used a median 0.10 of their bounds, but the long steps outran their estimates, so the projection is an upper bound of no later than 14:46 ET; the database is idle at 29 of 500 connections with none active, so the loads are client-bound and 250 connections needs more compute than an 8 GB machine (2026-11-18 08:18 ET; 43 tests)
  - [x] The operator's deadline: 2 hours from the start, 08:33 ET; the lanes were started by hand and will not finish by then (N-PORT security 1 h 40 min in, GLEIF 40 min). Asked what should happen at 08:33, the operator chose "Keep loading, report the miss" (2026-11-18 08:15 ET); the real total and each step's time are recorded here when the chain ends
  - [x] Learning → skill: data-operations (`--auto`, a fresh state file), data-platform (no agent or reviewer opens the stores folder), aws-snowflake-operations (a login needs TEMPORARY with CONNECT), the initialize runbook (planning the lanes to fit a window, `--auto`) and the daily-run runbook (read the machine before adding a load) (2026-11-18 07:50 ET)
- [ ] SEC company: started 2026-11-15 13:34 ET, 150 bundles, about 50 minutes expected (54 minutes hosted before)
- [ ] The rest of the 41 steps in order; each step's time and counts recorded here as it finishes
- [ ] The lookups built and each silver table's master ids filled (`--finish`)

## Done when

- [ ] Each target's counts recorded beside the local proof of the same capture: records, golden records, set aside,
  reviews, silver rows, links. A count that differs is explained before the next target.
- [ ] The time of every target, from its run, recorded here
- [ ] The GLEIF merge sampled in its first minutes: merge sessions waiting on a lock, and records a minute against 2,060
      (native Python, one process). Moved from ticket 233.
- [ ] Where two kinds merge at once (GLEIF companies beside N-PORT securities), records a minute each against 6,500 alone
      and 3,100 together. Moved from ticket 233; a full-size load is not run only for it.
- [ ] N-CEN fund series, advisers, share classes and registrants loaded (moved from ticket 234).
- [ ] A persons bundle's hosted seconds on current code (moved from ticket 239): locally 323 statements a bundle before the MDM
      ping was removed (about 21 fewer expected), about 14 s of round trips at 43 ms; the start was 118 s.
- [ ] Companies holding more than one CIK: expect 0 once N-PORT registrants load under `yields_to: [cik]` (moved from ticket
      234; the store held 4: 3 with 2 CIKs, 1 with 3). A bind already made stays standing, so this needs the registrants
      loaded into a fresh store, not reloaded over the old binds.
      The Company `lei` contract changed, so the processing identity of `gleif.level1.v1`, `iapd.adv.custodians.v1` and
      `sec.nport.registrant.v2` changed too: a load over a store that holds them reads them again.
- [x] Learning → skill: the Edgar Intelligence runbook (`docs/runbooks/edgar-intelligence.md`), "Initialize a hosted store" and "Load a fresh store"; the connection
  section; aws-snowflake-operations, "The hosted MDM store"; STORES, "Apply store DDL" (2026-11-15 13:45 ET)

## Hosted parts moved here (operator, 2026-11-17: "Review all open tickets, consolidate and close move hosted run to a single ticket")

Each part is struck in its own ticket with `deferred to 238`; the full text stays there. Read each when its step loads.

- [ ] [246] Hosted: the next chain run loads the source's files once more (its rules changed, so every file is processed again under the new identity), then a second run changes nothing, counted as the rerun above did. Not run: it reloads the N-PORT securities.
- [ ] [251] Hosted: resume the GLEIF load (`--workers 8`) on this code and measure records a second; the merge then ends in about 1.4 hours plus a restart's re-read of about 15 minutes.
- [ ] [248] The SEC ticker file copied into each OpenFIGI capture folder it loads (`openfigi/2026q2-nport`, `openfigi/form4-tickers-20261109`) with a receipt: additive, from the file already on this machine. Not done: it is part of the hosted run.
- [ ] [248] Hosted: the operator accepted the cost ("yes", 2026-11-16): OpenFIGI's 771,554 records load again. Still to be started on the operator's word to run it.
- [ ] [249] Hosted: needs the operator's word to run. It changes GLEIF's rules, so all 3,043,084 records load again and about 2.8 million Companies are created, with their lookups and links. Time not measured. The Rust extension must be rebuilt where the load runs.
- [ ] [240] Each grain measured as statements a bundle (`count_statements.py`) and hosted seconds, on the persons capture
- [ ] [240] The hosted store loads at `run` grain from the next load on (the hosted GLEIF load now running was started at `unit`); nothing is loaded again for the switch
- [ ] [212] GLEIF Level 1 (finds Companies, never creates), then GLEIF relationships
- [ ] [212] OpenFIGI, then 13F securities and N-PORT security (Securities)
- [ ] [212] SEC ownership (Form 4 relationships)
- [ ] [212] 13F filings
- [ ] [212] SEC company facts and SEC registration (Silver only)
- [ ] [212] Reconcile waiting links once both endpoints exist; record the totals
- [ ] [212] Load each source into the hosted store from the local captures, no AWS (2026-11-11 06:02 ET; operator: "after init load each source in snowflake from local no aws"). Done so far on the hosted store: GLEIF subfund pairs (1 document), N-PORT registrants (1),...
- [ ] [212] Hosted counts, first part done (2026-11-11 16:45 ET): ticket 209's count on the hosted store after the SEC company load (read-only, 102 s): 446,704 records with a golden record, 393,459 explained as creators, 53,245 by an identifier, 0 by a decision (the waterfall pass has not run there yet), **0 unexplained**, none for any source; 415,730 golden records. Still to record: each source's stored and set-aside counts, and the count again after the remaining sources load.
- [ ] [212] Hosted OpenFIGI answers load finishes inside the operator's 1 to 2 hour window.
- [ ] [212] [153] Counts (`local-staging`, read-only, 2026-11-11): 395,838 Security, 22,766 Company, 12,937 Fund Structure and 31,097 Person golden records; 1,271,374 source records, 0 unexplained. **Not true that no identifier sits on two masters:** 13 SEDOLs and 1 LOANX are each held by two Security masters (14 pairs), 364 tickers by two to four Securities, 231 LEIs by both a Company and a Fund Structure, and 1 CIK by both a Company and a Person. To decide: whether each of the 14 Security pairs is one security (merge) or two (the identifier is wrong on one), whether a ticker may sit on several Securities (it is a lookup, not a join key), and whether one LEI may name a Company and a Fund Structure.
- [ ] [212] Run `mdm migrate` on the hosted store once it exists: it carries every migration the local store has, including 005–007 (ticket 18) and 010 (ticket 19), moved here 2026-10-18 12:25 ET
- [ ] [253] The hosted GLEIF merge on the fresh store holds about 458 golden records a second (measured 2026-11-16 21:02 ET, 8 workers); record the figure again.
- [ ] Learning → skill: after the run, each skill line the run changed, or "none".
- [ ] [174] The fresh load loads `sec.prospectus` (chain step `prospectus`, capture `sec.prospectus/first-424b4`, copied to where the hosted load reads it) and `sec.registration` with its new Security link. The Company rule's version changed (a new listing is a Company), so `sec.company` processes every document once more on a store that holds it; a fresh store loads it once.

