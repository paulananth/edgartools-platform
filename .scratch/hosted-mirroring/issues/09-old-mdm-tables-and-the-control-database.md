# 09: The old MDM tables, by the seven wastes, and what belongs in the control database

Status: open

The operator, 2026-11-20: "Investigate and apply 7 wastes to the below and categorize what should be in the control
tables" (the `mdm` schema, 28 tables, and the `public.mdm_store_*` tables, 21, in the hosted data database).

Read on the hosted data database as the owner (counts and names only), and in the code on `main`. The control
database holds `bookkeeping` (pipeline_run, work_item, lease, checkpoint, journal_outbox), `journal.event` and
`rules.rules_used`.

## Findings

| Group | Tables | Rows | Who uses it | Waste | Where it belongs |
|---|---|---|---|---|---|
| Old engine's run control | `mdm.run`, `run_batch`, `batch`, `batch_change`, `checkpoint`, `attempt_event`, `outbox`, `outbox_event`; `mdm_store_run`, `_batch`, `_lease`, `_checkpoint`, `_outbox`, `_outbox_context` | 0 | nothing writes them; Bookkeeping in the control database does the same job | Inventory, over-production | delete (Bookkeeping is the control) |
| Old engine's master data | `mdm.stage_record`, `source_reading`, `current_record`, `master_entity`, `company`, `company_alias`, `detail_version`, `relationship_version`, `decision`, `set_aside_record`, `match_proposal`, `match_proposal_event`; `mdm_store_current`, `_history`, `_lookup`, `_authority`, `_proposal`, `_proposal_event`, `_evidence`; the 36 `mdm` views over them | 0 | replaced by `public.mastering_*`; read only by the old replay (`mastering/rebuild.py`), the per-kind views (`mdm/schema.py`) and the empty-store check (`mdm/store.py`) | Inventory, over-processing (two engines' schemas installed) | delete, with that code |
| Rules registry | `mdm.policy` (1), `mdm.dataset` (18), `mdm.dataset_mapping` (18), `mdm_store_pin` (38), `mdm_store_gate` (1) | 76 | `rules register` writes them; the merge worker, the links step and the load preparation read the policy by its digest (`registered_policy`) | Transport: a copy of the rules files, kept beside the data | control database, `rules` schema, beside `rules_used` |
| Kind list | `mdm.master_kind` (8) | 8 | `configure_kinds` at init, for the per-kind views | Inventory: a copy of `rules/merge/kinds/` | delete with the views; the kinds are the rules files |
| Install records | `mdm.migration` (2), `mdm_store_migration` (7) | 9 | init checks the installed function bodies by checksum | Over-processing: a migration history in a product that only inits | one init stamp with the data database's own schema (it describes that database), no history |
| Build record | `mdm_store_metadata` (1, `derived-index`) | 1 | `profile_load.py` reads run reports from it | Motion: run evidence outside Bookkeeping | control database (Bookkeeping holds run evidence) |

Kept in the data database: the merge's progress `public.mastering_file` and `mastering_delivery`. They are control-like,
but the merge marks a file done in the same transaction that writes its masters, and that needs one database.

## Checklist

- [x] Investigate both groups: counts on the hosted data database, the readers and writers on `main`, sorted by waste (table above) 2026-11-20 10:03 ET
- [x] Operator decision (2026-11-20): the rules registry moves to the control database's `rules` schema ("I recommend moving it to the control database's rules schema. Agreed") 2026-11-20 10:08 ET
- [x] Skill first: data-platform CONNECTIONS.md says the data database holds data and the control database how it is processed (the registered rules in `rules`, run evidence in `bookkeeping`), one init stamp, no empty table kept; skill lints pass 2026-11-20 10:08 ET
- [x] Operator decision (2026-11-20): the kind list is an RDM code set ("RDM code set (Recommended)"), after asking "Should kind be on RDM or MDM"; research (DAMA: reference data classifies other data; Reltio keeps entity types as model configuration and code lists in its RDM) and the identification tests are in data-profiling SKILL.md "Identify an MDM kind"; data-onboarding's new-domain step publishes the code with its rules file; skill lints pass 2026-11-20 10:21 ET
- [x] Finding (2026-11-20): three of the four kinds thought unused label held-back records as their probable kind, through the Company classification rules: on hosted, government 6,955, branch 1,913, international organization 87; venue labels none. Venue is RDM's `iso-10383-mic` on a Security's listing (25,974 Securities, 617,329 listings, 209 MICs on hosted), not a golden record (operator asked: "check if venue is being sourced from openfigi mic codes") 2026-11-20 11:44 ET
- [x] Operator decision (2026-11-20): keep government, branch and international organization as kinds with no golden records yet ("Keep the 3 (Recommended)"); only venue goes 2026-11-20 11:44 ET
- [x] Publish the RDM code set `mdm-kinds` version 1 (7 codes: code, label, definition, `golden_records`) in `rules/reference/published/`; the engine catalog pins it in place of its `kinds:` list and reads its kinds from it; the kind meanings left `rules/context/definitions.yaml` for the codes' definitions; identifiers stay in each kind's rules file (a copy would be transport); verified: `test_each_kind_holding_golden_records_has_one_rules_file_and_back`, `test_every_probable_kind_a_rule_names_is_a_kind`, `test_a_catalog_that_lists_its_kinds_is_refused`, unit, mdm and architecture suites, storage adapters 179 passed on PostgreSQL and on MySQL 2026-11-20 11:44 ET
- [x] Venue's glossary term (Market/Venue) left `CONTEXT.md`, and `mdm-relationship-types` version 6 drops the two types that name it (HAS_MARKET_OPERATOR, IS_SEGMENT_OF_EXCHANGE) under a new pin; the policy digest moved (fixtures repinned), the relationships Mapping Document regenerated, the catalog's venue domain gone; verified: `test_relationship_types.py`, `test_rules_catalog.py`, `test_rules_mapdoc.py`, `test_company_mastering_target_postgres.py` 2026-11-20 11:44 ET
- [x] Delete the old engine's `mdm` tables, views and kind list from init (`mdm/migrations/schema.sql` keeps `policy`, `dataset`, `dataset_mapping`, `migration`), with the code that reads them (`mastering/rebuild.py`, `mdm/schema.py`, the empty-store check, the `rebuild`, `rebuild-name-index` and `rebuild-detail-lookup` commands); verified: unit and mdm tests 2,965 passed, storage-adapter suite 179 passed on PostgreSQL and on MySQL, architecture and four integration files 110 passed 2026-11-20 11:19 ET
- [ ] Delete the old engine's `mdm_store_*` install (run, batch, lease, checkpoint, outbox, current, history, lookup, authority, proposal, evidence), with the registry move: the registry's pin and gate are `mdm_store_*` tables read through the same adapter
- [x] Move the registry to the control database's `rules` schema: `rules.policy` (each Mastering Policy under its digest) and `rules.dataset_reading` (each reading of a Dataset Contract, numbered from 1, with its registry version), made by `rules init`, only added to (the agent role reads, the registrar adds); the merge worker, links, preparation, the steward commands and `rules register` use it (`edgar_warehouse/rules/registry.py`); `mdm.policy`, `mdm.dataset`, `mdm.dataset_mapping`, the pin approvals and `mdm grant-registration` are gone; verified: `test_the_registry_keeps_each_policy_and_each_reading_and_the_runtime_only_reads_it` on PostgreSQL and MySQL, storage adapters 177 and 179 passed, Postgres integration 331 passed 2026-11-20 12:59 ET
- [ ] The build record (`mdm_store_metadata`): nothing writes run reports there, so `profile_load.py`'s reader of them goes with the governed storage; one init stamp in place of the two migration tables
- [x] Hosted, after the kinds PR (operator, 2026-11-20: "yes"): idle checked (no running run, no active session); `rules register` registered the policy of relationship types 6, the 18 contracts unchanged at reading 1; RDM published `mdm-kinds` 1 (7 codes) and `mdm-relationship-types` 6 (23 codes, superseding 5), each equal to its pin 2026-11-20 12:59 ET
- [ ] Hosted: re-init per the runbook, counts before and after; RDM holds `mdm-kinds` 1 and `mdm-relationship-types` 6, and the policy with version 6 is registered before the next load
- [ ] Learning → skill
