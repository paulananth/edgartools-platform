# 135: The recreation proof starts from configured Company records

Priority: 135, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md).
Opened 2026-10-22 from the map review ("review all existing ticket and provide a
way to complete the project").

Type: task. Status: in progress (Claude, 2026-10-29; operator, 2026-10-29 07:33 ET: "Take over 135").
Blocked by: nothing on this map (#1121 and #1142 merged).

## Question

[32: the recreation proof](32-profiling-08-recreation-proof.md) defers its
baseline and its cold-agent run to one unchecked item of the
`sec-configured-fields` workstream
(`.planning/workstreams/sec-configured-fields/TICKET.md`, line 9): "retire
Company preparation/census/provenance and GLEIF release/semantic consumers;
prove whole-source census and installed 6,414 Company / 3,052 CIK+LEI
population/recovery". Mastering starts from SEC Company records (GLEIF alone
binds nothing), and the Company input is still the retained Company
preparation that item retires; a baseline taken today would measure a path
about to be removed. Neither #1121 nor #1142 ticked it (checked 2026-10-22
21:11 ET).

What is left before 32's baseline can run:
- the Company records come from the configured source extract, combine and
  `mdm.prepare` chain, never the retained preparation;
- the census and provenance consumers read the configured outputs;
- the installed population proof repeats: 6,414 Companies and 3,052 CIK+LEI
  bindings from an empty store, a second pass changing nothing.

The item sits in another runtime's workstream file. Nothing is owned by Codex
(operator, 2026-10-16), and the overlap rule still applies: take it over only
on the operator's ruling, then build on Codex's merged work, never beside an
open branch.

## Checklist

- [x] Operator's ruling (2026-10-29 07:33 ET): "Take over 135": Claude takes the item over (asked 2026-10-22,
  then "skip this move to next"). No Codex PR is open (checked 07:35 ET); the overlap guard still runs on every commit
- [x] The item's remaining parts, from the workstream files (2026-10-29 07:35 ET): the item is
  `.planning/workstreams/sec-configured-fields/TICKET.md` line 9; its parts are spread over
  `company-preparation-cutover` and `whole-source-census`. On today's `main`:
  - Legacy record mapping: none left (`legacy_pair_comparison` and `legacy_jurisdiction_table` are configuration
    keys of the mastering catalog, not old code). Done.
  - Company preparation: configured since #880 (2026-10-09): `company_prepare.py` only binds the approved run
    IDs and the census digest into the `mastering` target's configured steps (read, combine, `mdm.prepare`,
    `mdm.merge`). Done.
  - The Name Frequency census (`mdm name-census`): still built in Python (`name_frequency.py`, `name_census.py`,
    GLEIF's input checked by `gleif_publication`), over configured readings; the whole-source comparison to
    original-source EOF passed (2026-10-09). Open in `whole-source-census`: "Express complete source census
    construction in bundled Rules, with immutable source/context receipts and separate worker verification",
    then replace its consumers and retire the Python construction
  - The installed population proof (6,414 Companies, 3,052 CIK+LEI from an empty store, an unchanged replay and
    recovery): passed 2026-10-10, -11 and -11 (#906 and the raw-capture bundles); MDM storage changed since
    (governed storage, #1152-#1190), so it runs again on today's `main` before 32's baseline
- [x] Narrowed (2026-10-29 07:50 ET; operator, 2026-10-29: "Yes clean up anything pending from codex", agreeing
  to narrow 135 to the proof): Codex finished the MDM migration (#1212); no live code calls the old native
  routines or schema (checked on main). Ticket 32's baseline needs only the installed population proof below:
  the census it reads is built from configured readings and was proven equal to the original sources to EOF
  (2026-10-09). The census build moving into Rules is ticket 148
- [ ] ~~The census construction as a configured Bookkeeping target in Rules~~ moved to ticket 148: not needed for
  32's baseline
- [ ] ~~The census consumers read the configured target's output; the Python construction retired~~ moved to
  ticket 148
- [x] The proof's inputs on today's `main`, and its expected answers written before the run (2026-10-29 18:27 ET):
  the harness is `.scratch/mastering-to-done/proof/installed_mastering_proof.py` (2026-10-12, kept current to
  #1066): each of the 14 `cm27-raw` document lists (6,726 Company documents) prepared by the installed `mdm
  prepare-clean-company` and merged by installed workers, then GLEIF, then a second pass. The 10-10 inputs it
  borrowed are gone (`cm27/bundles`, the GLEIF row cache, the checkout replay's binding pin); the GLEIF scope is
  rebuilt exactly: each cohort filer's current-name key (ticket 148's configured reading) looked up in the
  recorded census gives 3,755 LEIs, the 10-10 proof's number (`cm27-raw/gleif-rows-scope-20261029.jsonl`, local).
  Rule changes since 10-12 (16 commits on the Company, GLEIF and SEC submissions rules) leave the expected counts
  as they were: ticket 97's issuer rule acts only on records an N-PORT holding flags, and the proof supplies
  that set empty. Expected: 6,726 documents prepared; 6,414 SEC records staged and bound (312 wait, classification
  deferred); 6,414 Companies; 3,052 GLEIF records bound; the second pass changes nothing; the recovery's killed
  worker's item finished by a later attempt. The binding-pin comparison: its file is gone, but its digest is in the 10-10 harness (`CHECKOUT_BINDINGS`); reported, not asserted, since it was taken over the `mdm` tables' subjects
- [x] The harness on today's storage (2026-10-29 18:47 ET): MDM's records live in governed storage since #1152, so
  the 10-12 harness's counts read the empty `mdm` tables and its verifier could not read the storage's tables. A
  one-bundle run (bundle 1-1) passed with every count 0 and proved nothing; the harness now grants the verifier the
  `public` schema (as today's installed test does) and counts through the record reader (`inspection.counts` and
  each source record's current pointer). Rerun on bundle 1-1: 512 documents, 486 Companies bound, 26 classification
  deferred, the killed worker's item finished by attempt 2, a second pass unchanged
- [x] The installed population proof on today's `main` (2026-10-29 19:23 ET; 35 min, 18:48-19:23 ET), every expected answer met:
  14 bundles, 6,726 documents prepared by the installed `mdm prepare-clean-company`; **6,414 Companies** from an empty
  store; **6,414 SEC records bound** (312 wait, classification deferred); 3,716 GLEIF records staged, **3,052 bound**
  (664 wait for a binding, 39 unsupported identity kind); 9,466 bind decisions; the recovery's killed merge worker's
  item finished by attempt 2; prepared again, 0 documents named and 0 runs started, 6,726 recorded processed; the
  **second pass changed nothing** (the current records' digest, the outbox's 63 and the history's 10,529 equal); and
  the record-to-master bindings **equal the 2026-10-09 checkout replay's digest** (`9216cc18...`). Report local only
  (it holds no record values, but the run's identifiers stay on this machine)
- [x] Three-axis review (2026-10-29 19:34 ET). GoF: leave it (the harness loads the 10-10 harness by path for its GLEIF steps; it changed twice in total). Fixed: three equalities the ticket states were reported, not asserted; now asserted, and each held in this run's report: the bindings equal the 2026-10-09 digest (governed storage names a record's subject as the `mdm` tables did, so the comparison stands; the review expected it to fail, the run showed it equal), the second pass leaves the history's count and the current records' digest unchanged, and 3,716 GLEIF records staged; open Companies counted as on 2026-10-10, current Company entities with aliases left out (identities would also count a Company merged into another; this run made no merges, only 9,466 binds, so its 6,414 stands); each source-record pointer checked against its retained reading; the dormant pin comparison no longer names a key the snapshot dropped. Rerun on bundle 1-1 with the revised harness (6 min): 486 Companies, the second pass unchanged, every assert passing. Noted, not changed: the rebuilt GLEIF scope equals the 10-10 scope by count (3,755) and by the bound GLEIF records' digest, not by an LEI-for-LEI list (the 10-10 cache is gone)
- [ ] PR, CI green, merged
- [ ] 32's two deferred parts re-opened on this ticket's merge
- [x] Learning → skill (2026-10-29 19:23 ET): `skills/mdm-engineering/SKILL.md`, "Independent installed qualification": count a store through its record reader, never its tables; a proof whose counts are all zero proved nothing
