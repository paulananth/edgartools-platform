# 238: A fresh load into the hosted store, initialized again

Type: task. Status: open (the store is initialized; the chain is loading). Blocked by: none.

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
- [x] Learning → skill: data-operations RUNBOOK "Initialize a hosted store" and "Load a fresh store"; the connection
  section; aws-snowflake-operations, "The hosted MDM store"; STORES, "Apply store DDL" (2026-11-15 13:45 ET)
