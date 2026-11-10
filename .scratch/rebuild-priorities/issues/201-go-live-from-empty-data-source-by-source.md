# 201: Go live from empty data, source by source

Priority: 201. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 08:37 ET (operator: "We need a ticket to start everything from scratch for go-live with each source /wayfinder"; scope: "Just start empty for data not rules no proving").

Type: task, charted with wayfinder. Status: open. Blocked by: none.

## Destination

Every source has gone live from empty data stores. Rules stay, reference code sets (RDM) stay and captured files stay as they are. Only data is emptied: MDM masters and mastering records, Silver, Bookkeeping runs and the Change Journal. There is no proving step: no acceptance trace, no sample-then-full proof and no comparison run. Each source is loaded once through the real load, in the order of [the initial load sequence](../../../docs/initial-and-daily-source-load.md), and its counts are recorded.

## Out of scope

- Rules, RDM code sets and captured files (kept).
- Proving and comparison runs (operator: "no proving").
- New provider requests (the load uses captured files; each request needs the operator's word).
- Snowflake gold and any hosted environment.

## Sources, in load order

Each source: empty its data, load it from its captured files, record counts (files, records, masters, links waiting). One line ticked per source, with its ET stamp.

- [x] SEC company (Companies, by CIK) DONE (2026-11-10 00:27 ET): loaded on `local-staging` from the retained capture of 76,230 submissions documents plus the ticker catalog, with the existing Name Count file of 2026-11-04 (150 bundles of up to 512 documents, 2 at once, about 17 minutes of work in three runs). Counts: 5,091 Company golden records, 71,139 records set aside (phase 1: no ticker), 5,091 bind decisions (one per bound record), 150 files delivered; 5,091 + 71,139 = 76,230. `mdm reconcile --source sec.company.v1` closes (delivered 5,091 = golden records 5,091, set aside 71,139, 0 open reviews). No provider request was made.
  - FINDING (2026-11-10 00:27 ET): three things stopped the first runs, each fixed once; the three lines for the `data-operations` skill ("Load a capture") wait until Codex's open change to that file merges (the guard stops on `skills/data-operations/SKILL.md`): (1) the target's `run` takes `capture_run` as a fact as well as `--capture-run`; (2) a store created before PR 1577 had no `mastering_delivery` table, so every bundle failed at `mastering.merge`; the mastering schema install is idempotent and was applied with the migration login, plus SELECT for the verifier and governance logins; (3) `mdm reconcile` needs the worker login, not the verifier's. The earlier note that the SEC company load had to wait for a Name Count was wrong: the file of 2026-11-04 was built from this same capture and the load accepts it.
  - FINDING (2026-11-09 23:23 ET): the SEC company load cannot start as configured. `rules/sources/sec.company` declares the Name Count as a run file (`scripts/run_inputs.py sec.company`: facts capture_run, catalog_run, observed_at, load_mode; file name_count), and `edgar-warehouse mdm name-count` needs the whole SEC submissions population, a population list, a verified full GLEIF Golden Copy reading (`rules/sources/gleif/name-count-complete-stream.yaml`, 3.4M records) and its metadata, so GLEIF has to be read in full before SEC company can load. The capture (`mdm/captures/sec.submissions.company/all-76230`) and the ticker catalog are on the machine. Ticket 202 removes the file: the GLEIF merge searches the golden records by name itself. Two ways forward: (a) build the Name Count now (a full GLEIF read, then the SEC read), or (b) do ticket 202 first, which needs the operator's word on whether an earlier name binding stays when a later load makes the name shared (recommended: it stays, a steward splits it, decisions are never undone silently).
- [x] N-PORT registrant (Companies, by CIK) DONE (2026-11-10 05:12 ET): one document (the 2026 Q2 N-PORT archive), 1,947 registrants stored and 1,947 with a Company golden record; the store holds 7,035 golden records for 7,038 records, so 3 registrants joined Companies SEC company created, by CIK. `mdm reconcile` closes.
- [x] Form ADV filings and custodians (adviser and custodian Companies) DONE (2026-11-10 05:12 ET): two monthly files (March and June 2026), each through the filings target and the custodians target. Filings: 17,965 stored, 17,964 with a golden record, 1 waiting in a `conflicting_identifiers` review. Custodians: 2,246 stored (a custodian named in both months is one subject with two records), 2,194 with a golden record, 52 waiting with an open review, 34 set aside for an invalid LEI check digit. The June custodians needed `--revision 1` (a later month restates every custodian); the first June run stopped at merge with "contradictory publications" and is left as it is. `mdm reconcile` closes.
- [ ] GLEIF Level 1 (finds Companies, never creates), then GLEIF relationships
  - NOT STARTED (2026-11-10 05:12 ET): the GLEIF run takes two files, `approved_scope` (the LEIs to master) and `nport_issuers` (the LEIs N-PORT holdings name as issuers, which needs the N-PORT securities first), and a fact `publication_count`. Choosing the scope is a decision for the operator; recommended: the LEIs of mastered SEC, N-PORT and ADV Companies plus the issuer LEIs, since GLEIF only attaches and never creates.
- [x] SEC submissions person (Persons) DONE (2026-11-10 05:12 ET): 149 bundles from the same 76,231 documents: 31,097 Person golden records (the same count the shared store held), 45,134 set aside, `mdm reconcile` closes. The first run, 2 bundles at once, left 7 bundles stopped (a database deadlock in `source.read` and a stale lease); the same command with 1 bundle at once finished them with no failure.
- [x] N-PORT fund (Fund Structures) DONE (2026-11-10 05:12 ET): one document: 12,937 Fund Structure golden records, 7 set aside, `mdm reconcile` closes. The silver step `silver.derive` ran past the 60-minute window and finished when the same command was run again (a 90-minute window).
- [ ] OpenFIGI, then 13F securities and N-PORT security (Securities)
- [ ] SEC ownership (Form 4 relationships)
- [ ] 13F filings
- [ ] SEC company facts and SEC registration (Silver only)
- [ ] Reconcile waiting links once both endpoints exist; record the totals

## Prerequisites

From [the initial load sequence](../../../docs/initial-and-daily-source-load.md), steps 1 to 4. The doc's "what blocks the full load" table is older than the rebuild, so recheck each line before relying on it.

- [ ] ~~Capture inventory frozen: every retained SEC, GLEIF and OpenFIGI delivery with files, receipts and hashes (no provider request).~~ not needed: operator, 2026-11-09 11:20 ET: "Only" the registration check and the MDM setup rows are needed.
- [x] Rules documents loaded on `local-staging` (2026-11-09 10:16 ET): `rules load --root rules --version rules-2026-11-09.go-live` saved 15 versions (13 sources, 1 merge policy, 1 pipeline), all approved from `rules/approvals.yaml` in git with no test run, then `rules activate` (merge policy first, then the pipeline and each source, all with exit 0) left 15 of 15 active. Activation needs `governance.env` sourced beside `worker.env` for `RULES_MDM_ACTIVATION_DATABASE_URL`; without it `rules activate` stops with "MDM activation requires an explicit destination connection".
- [x] Rules refreshed on `local-staging` with today's rules (2026-11-09 23:12 ET; the first load predated the phase 1 classification, the custodian name-and-place rules, the Form 4 issuer-and-symbol rule and the bind decisions): `rules load --root rules --version rules-2026-11-10.go-live` saved the 15 documents and approved each from `rules/approvals.yaml` (merge policy digest 5817f4fb, finalized PR 1586), then `rules activate` merge policy first, the pipeline, then the 13 sources: all exit 0. The CLI in the main checkout's `.venv` has a stale compiled extension (`source_contract.prepare_relationship_types` missing), so the load ran the main checkout's code with the arm venv's built extension. No data was loaded.
- [x] RDM code sets restored with exact version pins on `local-staging` (2026-11-09 11:04 ET; operator: "Yes, restore all 11 as published (Recommended)"). All 11 published code sets in git (14 versions, four of them of `mdm-relationship-types`) were drafted from their canonical files, approved in those words, published, and each sha256 equals its `pin.json`. The first try dropped the `properties` column and 6 pins differed; a published version cannot be redrafted, so the store was dropped and rebuilt (Rules reloaded, 15 of 15 active) rather than retiring them. The restore is now a script, `skills/data-operations/scripts/rdm_restore_published.py`, run on a throwaway store: 14 of 14 pins ok, exit 0.
- [ ] Skill gaps from the rules step: `data-operations` step 2 says "`rules load` saves every file under a root; do not use it here" and step 3 omits `governance.env`, while the go-live path for a new store is `rules load` then `rules activate` with `governance.env` (as `data-onboarding` APPROVE.md says); make the skills agree.
- [x] Each source registered on the new store (read-only, 2026-11-09 11:20 ET): all 14 configured Dataset Contracts are registered in MDM (`mdm.dataset` 14, none missing, none extra) and 14 are mapped (`mdm.dataset_mapping`); one merge policy (`mdm.policy` 1) and the 8 master kinds are in place; Rules 15 of 15 active.
- [x] MDM setup rows identified (read-only, 2026-11-09 11:20 ET): MDM tables holding rows are `mdm.dataset` 14, `mdm.dataset_mapping` 14, `mdm.master_kind` 8, `mdm.migration` 30, `mdm.policy` 1 and the governed store's `mdm_store_gate` 1, `mdm_store_metadata` 1, `mdm_store_migration` 7 and `mdm_store_pin` 30. All are registration, migration and pin records; every mastering table is empty.
- [ ] ~~Name counts built from whole populations: the full SEC submissions, the ticker catalog and the full GLEIF Level 1 publication.~~ not needed: operator, 2026-11-09 11:20 ET: "Only" the registration check and the MDM setup rows are needed.
- [ ] ~~Sources with an incomplete path named, not omitted: N-PORT run builder (ticket 79), OpenFIGI listing enrichment (ticket 80), and complete mastering targets for ADV, ownership and 13F.~~ not needed: operator, 2026-11-09 11:20 ET: "Only" the registration check and the MDM setup rows are needed.
- [ ] Ticket 199's open parts that a fresh load meets: the rules version recorded on mastering records, and the Silver `links` stale-lease stop seen in the GLEIF loads.
- [ ] Ticket 02's origin check of the 327 governed-store runs done first, since an empty start erases that evidence.

## Init, decided

- Environment (operator, 2026-11-09 08:42 ET: "I recommend a new store. Call it local-staging"): a new store named `local-staging`, not the shared `local-test-server`. A new store leaves the current stores as they are, so no backup is needed first.
- Bookkeeping and the Change Journal start empty (operator, 2026-11-09: "Empty bookkeeping, empty change journal", "This is for ticket 201 init"). MDM and Silver data start empty too.
- [x] Initialize the store from the skills alone (2026-11-09 08:46 ET). First try failed on gaps in the skill (no interpreter in the command, a checkout behind `origin/main`, a store tied to its creating checkout, a stale skill link); `local-staging` was dropped, the skill text fixed in a working copy, and the retest passed in 17 s: six stores, Bookkeeping, Change Journal and Silver without rows, MDM with six setup tables holding rows. The skill fix waits on the overlap guard (another runtime edits `skills/data-operations/SKILL.md`).

## Open decisions, to settle one at a time

- [x] Environment: `local-staging`, a new store (see Init, decided). Backup of the current stores: not needed.
- [ ] Whether a source that cannot yet load (ticket 79 N-PORT run builder, ticket 80 OpenFIGI listing enrichment, ADV and 13F mastering targets) is deferred or loaded as far as its path supports. The load sequence says to report the missing source and stage, not to omit it.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".

- [x] FOUND at the go-live (2026-11-10 10:44 ET): activating the merge policy on `local-staging` was refused: "Rule version already registered with different steps" for 7 rules (`nport-registrant-cik` and six OpenFIGI rules), because their source codes moved (`openfigi.security.v4`, `sec.nport.registrant.v2`) under the same rule versions. A rule version is immutable once registered. Fixed: each has a new descriptive version (`2026-11-10.source-v4`, `2026-11-10.registrant-v2`), approval line finalized as PR 1617. The guard check `scripts/dev/dataset_identity.py` now compares each merge rule with its version at the base; on PR 1613 against its parent it names exactly the 6 security rules, on this change it passes.

