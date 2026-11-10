# 207: Step 4: join, create, or two found

Priority: 207. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 14:34 ET (operator: "Create ticket for each step and prove it to me that it works start with step 1").

Type: task, with a proof. Status: open. Blocked by: none.

## Question

Does the engine do this, and can each part be shown to work?

## The approved step

One golden record found: the source record joins it. None found by any identifier or by the name rule: the entity type's creation rule creates one golden record, or leaves the record waiting. Two golden records found: this is an error, a duplicate already in the store. Mastering runs its matching rules on the two golden records. If they match, the younger is decommissioned, and the older survivor keeps both golden records' identifiers, source records and history, and the source record joins the survivor. If they do not match, the source record stays unjoined with an exception status until a data steward resolves the duplicate.

(CONTEXT.md, "Mastering", approved by the operator one step at a time, 2026-11-09.)

## Where it lives today (from reading `edgar_warehouse/mastering/merge.py`, 2026-11-09 14:34 ET)

One found binds it. None found either mints (`on_no_match: mint`) or waits. Two found: `store.oldest` keeps the older, `repoint` moves the records, the younger becomes an alias. Not verified: that the matching rules run on the two before they merge, and the unjoined exception status when they do not match.

## Checklist

- [x] Prove one found joins, with a test. DONE (2026-11-09 22:30 ET): `tests/storage_adapters/test_mastering_join_create_merge.py::test_none_found_creates_...` (PostgreSQL 16 and MySQL, 6 passed): after the first record creates, a second with the same identifier joins it and no golden record is added, for each of the four entity types.
- [x] Prove none found mints or waits as the entity type's creation rule says, one test per entity type. DONE (2026-11-09 22:30 ET): the same file: company, person, fund structure and security each create one golden record of their own entity type with no review; `test_none_found_waits_where_the_rule_says_wait_and_creates_nothing`: a GLEIF record with no Company to attach to waits and creates none (`test_a_record_with_no_match_waits_as_an_open_review` also asserts its open review). Security and Person sources have no wait rule today, so only Company waits.
- [ ] Prove two found runs the matching rules first, then keeps the older and keeps both golden records' identifiers, source records and history. PARTLY DONE (2026-11-09 22:30 ET): `test_two_found_are_merged_the_older_kept_and_nothing_is_lost`: a record whose two FIGIs find two Securities merges them under the Security merge rule; the older survives, keeps both FIGIs, every source record of both is bound to it, and the younger is an alias of it. The decision history is step 6 (ticket 209). Only the Security rules merge today; for Company, Person and Fund Structure two found goes to review, which is the next part.
- [x] Prove two found that do not match leaves the source record unjoined with an exception status, and that a data steward can resolve it. FINDING (2026-11-09 22:30 ET): two found that are not merged are left unjoined with an open review `conflicting_identifiers` (proved in `tests/integration/test_mastering_identifiers_together.py`, PR 1591). No command resolves that review: the only steward command is `mdm steward split`, which undoes a merge. Resolving a review (merge the two, or exclude the pair so it is never proposed again) is unbuilt. DONE 2026-11-10 09:06 ET: the left-unjoined proof was already in `tests/integration/test_mastering_identifiers_together.py`; the steward resolution is proved by the tests named in the next part.
- [x] New (found 2026-11-09 22:30 ET): a steward command that resolves a `conflicting_identifiers` review, either by merging the two golden records (older survives) or by recording that they are not the same (a Match Exclusion), with a test of each. IN SCOPE (operator, 2026-11-10 07:55 ET: "Yes, build it (Recommended)"): 17 `conflicting_identifiers` reviews (27 records) from the share class rule need it. DONE 2026-11-10 09:06 ET: `edgar-warehouse mdm steward resolve --subject S --result merge|exclude --by --reason --policy-digest [--confirm]` (shows what it would do; writes only with `--confirm`). `merge`: the golden records the record reached become one (the older survives, merged by the same code a rule uses) and the record joins it. `exclude`: the record gets a golden record of its own without the identifiers that reached the others (kept as `<identifier>_held_by_another` evidence), each pair a Match Exclusion. Both record a bind decision with the steward and the reason, close the review and rewrite the golden record. Tests: `tests/storage_adapters/test_mastering_steward_resolve.py` (5 tests on PostgreSQL 16 and MySQL: preview writes nothing; merge joins; merge makes two reached golden records one; exclude gives its own and the exclusion; refusals), `tests/unit/test_mdm_cli_commands.py` (the command wiring). The second part above ("a steward can resolve it") is proved by the same tests.
- [x] Learning → skill: name the skill line this ticket changed, or write "none". DONE (2026-11-09 22:30 ET): none.
