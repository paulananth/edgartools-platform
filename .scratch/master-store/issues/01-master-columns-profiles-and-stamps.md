# A master's columns, its profiles in their own table, and no fact stored twice

Status: open
Type: task

The link build read 1.59 GB of master text for 28 MB of the three fields it uses. Measured on a 1% sample of the hosted
store: `fields` is about 5,600 of a master's characters, of which each value is about 23 and its attribution and two stamps
(`policy_digest`, `kind_version`, the same on every field) the rest; `entity_id`, `identifiers` and `subjects` repeat the key,
`mastering_identifier` and `mastering_record`; profiles are held by 0.5% of masters.

## Parts

- [x] Operator: "need to fix this before the db work , can profiles be on a seperate table, are there any other fields on json"; then "Approved, do 1 2 3 and check 4"; then "Yes include 4". 2026-11-19 21:48 ET
- [x] Checks on the hosted store, counts only: body identifiers equal `mastering_identifier` in all 10,018 sampled masters; body subjects equal the bound records in all 10,116; both lists always sorted; no master's fields carry two stamps (0 of 32,748), and survivorship stamps a master once (`prepare_master_records` takes one `policy_digest`, `field_values.rs` one kind version). 2026-11-19 21:48 ET
- [x] Skill: mdm-engineering `MASTER-FIELDS.md` (measure first; columns for what readers select by; a table for what a master holds many of; a fact once; a stamp once; one place splits, one assembles; prove the split), with its heading in `SKILL.md`. 2026-11-19 21:48 ET
- [x] GoF consult: the shape stands; split and assemble are pure functions in their own module (`mastering/master_row.py`). 2026-11-19 21:48 ET
- [x] 1. Columns `kind`, `status`, `canonical_id` on `mastering_master`; 4. `policy_digest`, `kind_version` once per master. The change test compares the text and the columns. 2026-11-19 21:48 ET
- [x] 2. `mastering_profile`: one row per profile, in order; `master_states` reads the columns and these rows, never the text. 2026-11-19 21:48 ET
- [x] 3. No `entity_id`, `identifiers` or `subjects` in the text; the write deletes identifier rows a master no longer holds; the text keeps a digest of what moved, so a change to it still moves the master's change number, and assembly refuses rows that drifted. 2026-11-19 21:48 ET
- [x] Proof: `tests/storage_adapters/test_mastering.py::test_every_master_assembles_to_what_survivorship_gave_through_create_join_change_merge_and_split` (assembled equals survivorship's body after create, join, change, merge and alias, split); with the stamps dropped from assembly it failed at "create". Round trip and refusals: `tests/unit/test_master_row.py` (9). Mastering adapter suites 61 PostgreSQL, 54 MySQL (7 skipped); 94 integration tests that read masters; unit and architecture 1,834. 2026-11-19 21:48 ET
- [x] Gold's base view reads the columns; the name stays read from the text (`tests/unit/test_gold_views.py`, 15). 2026-11-19 21:48 ET
- [ ] The hosted store takes the new shape at its re-initialization (the one-database work, `.scratch/hosted-mirroring/issues/04`); no migration
- [ ] Merge the PR when CI is green
- [x] Learning → skill: mdm-engineering `MASTER-FIELDS.md`. 2026-11-19 21:48 ET
