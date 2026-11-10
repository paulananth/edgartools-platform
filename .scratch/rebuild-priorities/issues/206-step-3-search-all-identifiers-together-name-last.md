# 206: Step 3: search all identifiers together, name last

Priority: 206. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 14:34 ET (operator: "Create ticket for each step and prove it to me that it works start with step 1").

Type: task, with a proof. Status: open. Blocked by: none.

## Question

Does the engine do this, and can each part be shown to work?

## The approved step

Mastering searches the cross-reference table for all the identifiers the source record states, together, under each identifier's Identifier Contract: who issues the value, how many golden records one value may name, and how many values one golden record may carry. Where the record states no identifier, or none finds a golden record, the name rule applies as a last resort: name, former name and place, each an approved rule with its own proof, and a name binds only where it is unique on both sides.

(CONTEXT.md, "Mastering", approved by the operator one step at a time, 2026-11-09.)

## Where it lives today (from reading `edgar_warehouse/mastering/merge.py`, 2026-11-09 14:34 ET)

`_match_identifiers` searches every identifier a record states. Names run after identifiers (`_match_names`, `_match_exact_names`). `_match_exact_names` already searches golden records by name and joins on exactly one. The three GLEIF name rules still read a precomputed Name Matching file (ticket 202). Former names are used by no Company rule today (ticket 203).

## Checklist

- [x] Prove a record stating two identifiers is searched on both together: a test where each identifier alone finds a different golden record. DONE (2026-11-09 22:23 ET): `tests/integration/test_mastering_identifiers_together.py::test_a_record_stating_two_identifiers_is_searched_on_both_together` (PostgreSQL 16, passed): a Form ADV filing stating a CIK one Company holds and a CRD another holds joins neither and goes to review `conflicting_identifiers` (step 4); a filing stating only the CIK joins the first with no review, so a search on the CIK alone would have joined it without notice.
- [x] Prove each Identifier Contract limit (issuer, forward, reverse) with a test that breaks it. DONE (2026-11-09 22:23 ET): already tested, each with a case that breaks it: issuer, `test_a_record_from_a_source_that_does_not_issue_the_identifier_adds_none` and `test_each_feed_maps_only_the_identifiers_it_issues`; forward (one value, two golden records), `test_one_value_held_by_two_securities_is_ambiguous_under_a_rule_that_does_not_merge` and `test_values_on_two_securities_wait_for_review_under_a_rule_that_does_not_merge`; reverse, `test_a_master_over_its_reverse_limit_goes_to_review` and `test_a_master_holds_any_number_of_values_when_the_contract_sets_no_reverse_limit` (`tests/mdm/test_identifier_lists.py`, `tests/mdm/test_cik_contract.py`).
- [ ] ~~Prove a name is tried only when no identifier finds a golden record, and binds only on exactly one golden record (ticket 202 rewrites the GLEIF name rules to search).~~ moved to ticket 204 (step 1) (2026-11-09 17:42 ET; operator: "This should move to step 1"). The order of the search, name only when no identifier finds a golden record, stays here.
- [x] The order of the search, name only when no identifier finds a golden record (DONE 2026-11-09 22:23 ET): `test_a_name_is_tried_only_when_no_identifier_finds_a_golden_record`: a custodian record stating a LEI one Company holds and a name another Company holds joins the LEI's Company, with no review.
- [ ] Name former name and place as separate approved rules, each with its own proof (ticket 203).
- [ ] Decide whether `composite_figi` (30,154 OpenFIGI records) or `share_class_figi` (35,872) is searched with the other identifiers to join listings of one Security; today only `figi` is. Found by ticket 204's list of keys stored and never searched, 2026-11-09 18:49 ET.
- [x] Learning → skill: name the skill line this ticket changed, or write "none". DONE (2026-11-09 22:23 ET): none.
