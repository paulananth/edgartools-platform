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

- [ ] SEC company (Companies, by CIK)
- [ ] N-PORT registrant (Companies, by CIK)
- [ ] Form ADV filings and custodians (adviser and custodian Companies)
- [ ] GLEIF Level 1 (finds Companies, never creates), then GLEIF relationships
- [ ] SEC submissions person (Persons)
- [ ] N-PORT fund (Fund Structures)
- [ ] OpenFIGI, then 13F securities and N-PORT security (Securities)
- [ ] SEC ownership (Form 4 relationships)
- [ ] 13F filings
- [ ] SEC company facts and SEC registration (Silver only)
- [ ] Reconcile waiting links once both endpoints exist; record the totals

## Prerequisites

From [the initial load sequence](../../../docs/initial-and-daily-source-load.md), steps 1 to 4. The doc's "what blocks the full load" table is older than the rebuild, so recheck each line before relying on it.

- [ ] ~~Capture inventory frozen: every retained SEC, GLEIF and OpenFIGI delivery with files, receipts and hashes (no provider request).~~ not needed: operator, 2026-11-09 11:20 ET: "Only" the registration check and the MDM setup rows are needed.
- [x] Rules documents loaded on `local-staging` (2026-11-09 10:16 ET): `rules load --root rules --version rules-2026-11-09.go-live` saved 15 versions (13 sources, 1 merge policy, 1 pipeline), all approved from `rules/approvals.yaml` in git with no test run, then `rules activate` (merge policy first, then the pipeline and each source, all with exit 0) left 15 of 15 active. Activation needs `governance.env` sourced beside `worker.env` for `RULES_MDM_ACTIVATION_DATABASE_URL`; without it `rules activate` stops with "MDM activation requires an explicit destination connection".
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
