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
- [ ] Publish the RDM code set `mdm-kinds` (the four kinds that hold golden records: code, label, definition, identifiers) in `rules/reference/published/`; a test ties each code to exactly one `rules/merge/kinds/<kind>.yaml` and back; the engine reads its kinds from it, and the `kinds:` list of `rules/mastering/engine-v1.yaml` goes, with the four kinds nothing uses; each kind's meaning moves from `rules/context/definitions.yaml` to its code's definition; the skills (data-modeling, data-onboarding MAP.md and REFERENCE.md) and CONTEXT.md "Kind" already say so
- [ ] Delete the old engine's tables, views and kind list from init (`mdm/migrations/schema.sql`, the `mdm_store_*` install), with the code that reads them (`mastering/rebuild.py`, `mdm/schema.py` views, the empty-store check)
- [ ] Move the registry and the build record per the decision; one init stamp in place of the two migration tables
- [ ] Hosted: re-init per the runbook, counts before and after
- [ ] Learning → skill
