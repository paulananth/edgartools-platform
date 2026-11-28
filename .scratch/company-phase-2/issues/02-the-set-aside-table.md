# The Set Aside table

Status: open
Type: task
Owner: claude (map decisions 10, 14)

The finish writes `silver.set_aside`: one row per identifier of a record a classification rule held back by decision
(any `classification_*` verdict), keyed as Gold's links resolve (namespace, value), with the feed, the reason and the
Probable Kind. The mirror carries it; no field of the record goes with it.

## Checklist

- [x] GoF consult (risky-reviewer): no pattern; three seams: `adapters.record_identifiers` taken out of `normalize`, `Store.held_back` beside `bindings`, `links.set_aside` landing through the silver writer's own snapshot (`land`), so PostgreSQL and MySQL share one path; the snapshot is not shared with `bind`, which is SQL for its 4.4 million rows (2026-11-27 21:35 ET)
- [x] `rules/silver/silver-set-aside.yaml` (key namespace, value, source code; snapshot; may be empty), registered at init with the other `rules/silver` specs, and checked by the loader before the finish (`loading.py`) (2026-11-27 21:35 ET)
- [x] A table of records no master holds says so: `holds_no_master: true`, a fourth way beside links, master columns and master_through (`test_a_table_may_declare_master_columns_or_the_table_it_carries_the_key_of[more2]` and `test_a_table_finds_its_master_one_way_and_names_real_columns[more4, more5]` failed on today's `spec.py`, 3 failed) (2026-11-27 21:35 ET)
- [x] The finish builds it after `master_binding` (`links.build` returns its count). Storage tests on PostgreSQL and MySQL, MDM and silver in their own databases: a held-back record's formatted identifiers and nothing else, a waiting reason is no Set Aside, a listed identifier gives a row each, a nested path (`entity.lei.$`), a record no longer held back leaves, a feed with no contract or a refused identifier adds none, one identifier of two feeds is two rows (`tests/storage_adapters/test_set_aside_table.py`: PostgreSQL 3 passed, MySQL 3 passed; each fails today with `AttributeError`, no `links.set_aside`); the finish's integration tests 2 passed; unit tests 228 passed (2026-11-27 21:35 ET)
- [x] On the exposure list and in `sources/managed-mirror.yaml` (25 tables); `verified: false` until the live mirror holds it (the readiness gate's `MIRRORED` refuses a load until then) (2026-11-27 21:35 ET)
- [x] Proved on the hosted store's held-back records, read only, nothing written: 704,950 rows, GLEIF 589,564 LEIs, the company feed 69,756 CIKs, the person feed 45,133, reporting owners 497; no feed without a contract, no identifier refused. Cost measured: whole bodies 3.26 GB through the network (2 min from the Mac); cut in the database to the identifier paths, 32.9 s on the server (2026-11-27 21:35 ET)
- [ ] On the hosted store before the next load: `silver register rules/silver/silver-set-aside.yaml` (schema owner) and the mirror's `alter` to add it, then readback and `verified: true` (ticket 07)
- [x] `/code-review`, three axes on `risky-reviewer` (Standards, Spec, GoF). Fixed: the finish's fake store lacked `held_back_sources` and `held_back(paths)`; one refused identifier dropped the record's good ones (each identifier is now read alone: the new case in `test_a_record_no_longer_held_back_leaves_the_table_and_a_refused_identifier_drops_only_itself` failed on the old skip with `assert 1 == 2`); a path part spelled `null` falls back to the whole body; the held-back filter is one constant on the store; `classification_not_activated` tested; the copied table count left the mirror test. Left: one links list for `loading.py` and `links.py` (GoF, optional until the list grows again); a second Rules engine for the adapter lookups (one connection a build). Storage tests PostgreSQL 3 and MySQL 3 passed, unit and integration 136 passed (2026-11-27 21:35 ET)
- [ ] The operator's ruling on `holds_no_master`: the rule "every silver table joins its master" has no exception yet; the table could instead be `mdm.set_aside`
- [x] Learning → skill: `skills/data-operations/HOSTED-LOADS.md`, the finish builds `set_aside` beside `master_binding` and what it costs (about 33 s for 705,000 held-back records) (2026-11-27 21:35 ET)
