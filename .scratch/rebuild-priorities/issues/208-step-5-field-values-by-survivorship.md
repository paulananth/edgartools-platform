# 208: Step 5: field values by survivorship

Priority: 208. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 14:34 ET (operator: "Create ticket for each step and prove it to me that it works start with step 1").

Type: task, with a proof. Status: resolved. Blocked by: none.

## Question

Does the engine do this, and can each part be shown to work?

## The approved step

Field values are chosen by survivorship, one field at a time, after the golden record is settled. Source priority, declared per entity type in the mastering policy, decides which source's value survives. It plays no part in deciding which golden record a source record belongs to. Every source's value, including the ones that did not survive, is kept.

(CONTEXT.md, "Mastering", approved by the operator one step at a time, 2026-11-09.)

## Where it lives today (from reading `edgar_warehouse/mastering/merge.py`, 2026-11-09 14:34 ET)

`_write_masters` calls `prepare_master_records` with the policy's source priority after the match. `check_source_priorities` validates it. Not verified: that every losing value is kept.

## Checklist

- [x] Prove source priority never changes which golden record a record joins: the same records in two priority orders give the same golden records. DONE (2026-11-09 22:35 ET): `tests/storage_adapters/test_mastering_survivorship.py::test_the_ranking_never_changes_which_golden_record_a_record_joins` (PostgreSQL 16 and MySQL): the same records under the policy's source order and its reverse give the same golden record with the same source records; only the winning name moves. Company, person and security.
- [x] Prove the winner per field follows the policy, one test per entity type. DONE (2026-11-09 22:35 ET): `test_the_first_ranked_source_wins_the_field_and_every_other_value_is_kept`: company (SEC over Form ADV), person (submissions over ownership) and security (OpenFIGI over 13F over N-PORT) each take the first-ranked source's value. Fund structure has one source today (N-PORT fund), so it has no ranking to test.
- [x] Prove every losing value is kept and can be read back. DONE (2026-11-09 22:35 ET): the same test: each losing source's value is in the field's `conflicts` with its source code (company 1, person 1, security 2).
- [x] Learning → skill: name the skill line this ticket changed, or write "none". DONE (2026-11-09 22:35 ET): none.
