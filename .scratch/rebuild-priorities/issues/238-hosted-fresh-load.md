# 238: A fresh load into the hosted store, initialized again

Type: task (a plan; nothing runs until the operator says so). Status: open. Blocked by: the gates below.

## Why

Operator, 2026-11-15: "do not load local-test-server, i need a plan to load fresh copy, re initalised in snowflake
hosted postgress". The rework of every source extract (ticket 235) and the two-path split (ticket 237) changed what
each source's rules are, so every source loads again anyway; the hosted store also holds loads from older code
(2026-11-11 to 2026-11-13) and an unrotated credential set. A fresh store loaded once, in order, from today's code is
simpler than reprocessing on top of it.

## What "fresh" means

- **Emptied:** MDM masters and records, silver, Bookkeeping runs, the Change Journal.
- **Kept:** the rules in git, the RDM code sets (restored from git), the captured files on this machine. No provider
  request: every load reads a capture already here.
- **Initialized again:** the hosted databases, their owners, roles, logins and grants, the schemas, RDM codes and
  source registrations, by the runbook ("Initialize a hosted store", `skills/data-operations/RUNBOOK.md`).

## Gates (each needs the operator's word; none is taken from an earlier ruling)

- [ ] **Credentials rotated.** The `mdm_runtime` password leaked earlier, and the hosted connection files still carry
  the credential set they had on 2026-11-12. A rotation of every hosted login (the admin and application credentials
  by `bootstrap-prod-mdm.sh`, the worker, registration and silver logins through the central connection section) comes
  before any load. Evidence: new connection files in `~/.config/edgartools/hosted/` whose credentials differ.
- [ ] **No one else uses the hosted store during the reset.** The rule: never stop, restore or replace shared data
  while others use it. Codex's work touches it (the hosted catalog sync; the draft Iceberg mirror, PR 1805, plans a
  hosted proof). Confirm with the operator that both are paused, and that the mirror's hosted proof waits for the fresh
  store.
- [ ] **What the old store's evidence is worth.** A reset erases the retained Bookkeeping runs that the load-timeline
  measurement (`.scratch/measure-prod-mdm-loads`) reads. Either finish that retrospective report first, or record that
  it is dropped. Recommendation: drop it; the fresh load is measured as it runs (below), on today's code.
- [ ] **Qualification.** `docs/specs/mdm/acceptance.md` and `state-of-build.md` defer Snowflake Postgres
  qualification. Recommendation: this fresh load, with its counts against the local proofs, is the qualification
  record; the operator says whether it counts.

## Decisions to take, one at a time

1. **Reset the databases or make a new instance.** Recommendation: keep the instance (its network policy, host and
   compute stay) and drop and create again the hosted databases inside it. A new instance gives new credentials too,
   but leaves an old instance to remove, and its host changes in every connection file.
2. **Backup before the drop.** Recommendation: none. Everything in the store is made again from git and the captures;
   the operator has asked for a fresh copy, not a restore point.
3. **Scope of SEC ownership and 13F.** Only cohorts are captured here: ownership 5,356 files (`p07-cohort`), 13F
   securities 52 information tables (`p07-cohort`), 13F filings `p07-managers`, registrations `s1-f1-originals`. The
   load takes everything captured; a full-history capture is a provider request and needs its own word.
   Recommendation: load the cohorts now, and capture the rest as a separate ticket.
4. **GLEIF.** 3.4 million records. Its hosted merge ran at 632 records a minute before the review-lookup fix (about 87
   hours); the fix's hosted speed is not measured, and batches of one kind still merge one at a time (ticket 233,
   stopped before building). Recommendation: start GLEIF after SEC company and measure its first batches; if the
   estimate is over a day, stop and take ticket 233 first.

## Before the reset (local, no hosted write)

- [ ] `rules/source-sequence.yaml` names one target a source; the split targets are not in it: `iapd.adv` custodians
  and silver, `sec.ownership` silver and security_symbols, `sec.thirteenf.securities` silver, `sec.nport.security`
  silver and mastering_other_keys, `gleif` subfund-pairs. Add each with its `after`, so the order is read from the file,
  not from this ticket.
- [ ] Each source's capture folder and run facts listed with `scripts/run_inputs.py` (facts such as `period`,
  `published`, `capture_run`, `catalog_run`), and the revision of each later delivery (Form ADV June, N-CEN
  quarters after the first): a second delivery of one source is `--revision 1` and so on.
- [ ] `load --plan` for every target against an empty local store, to see bundles and documents before any hosted
  time is spent.
- [ ] The Mac stays awake for the whole load (`caffeinate -dimsu` beside the loader); a sleep dropped the hosted
  connection before (74 minutes lost). Disk: 155 GB free today; N-PORT security needed about 32 GB.

## Initialize (hosted; runbook steps 1 to 7, after the gates)

- [ ] Drop and create the hosted databases (decision 1); owners, restricted roles and the Bookkeeping control group.
- [ ] Schemas: each store's `schema.sql` through `migrate`; every file prints its checksum.
- [ ] RDM codes: `rdm_restore_published.py`; every pin reads `pin ok`.
- [ ] Registration login; `rules check`, then `rules register`: a digest for the merge rules and every Dataset Contract.
- [ ] Worker logins and grants; `doctor` prints `"ok": true` under the worker connection; `load --plan` reads a capture.

## Load (hosted; one target at a time unless the order allows two, from the source sequence)

Times measured on the hosted store before are given; the rest are guesses until each target's first bundle is
timed (sample it in its first two minutes; say the estimate before going on).

- [ ] 1. SEC company (`all-76230`, 76,380 files; hosted 54 min, 2026-11-13).
- [ ] 2. GLEIF mastering (3.4 million records; decision 4), then GLEIF subfund-pairs.
- [ ] 3. SEC submissions persons (the same 76,230 documents).
- [ ] 4. N-PORT registrant (2026q2), then N-PORT fund.
- [ ] 5. Form ADV: mastering, custodians and silver for March, then June (`--revision 1`).
- [ ] 6. N-CEN registrant, adviser, fund and class, 2025q4 to 2026q3 in order (class after N-PORT security).
- [ ] 7. OpenFIGI (2026q2 answers, 7,714 files in 16 bundles; one hosted bundle took over 60 min before the round-trip
  fixes) and the Form 4 tickers.
- [ ] 8. 13F securities: mastering, then silver.
- [ ] 9. N-PORT security (2026q2): mastering, then mastering_other_keys, then silver.
- [ ] 10. SEC ownership: mastering, silver, then security_symbols (after OpenFIGI).
- [ ] 11. Silver only: company facts, 13F filings, registrations.
- [ ] 12. `silver refresh-ids` on each silver table that landed before its masters; the waiting links reconciled.

## Done when

- [ ] Each target's counts recorded beside the local proof of the same capture: records, golden records, set aside,
  reviews, silver rows, links. A count that differs is explained before the next target.
- [ ] The time of every target, from its run, recorded here (the measurement the reset erased, made again).
- [ ] Learning → skill
