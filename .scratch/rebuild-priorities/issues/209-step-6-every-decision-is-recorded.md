# 209: Step 6: every decision is recorded

Priority: 209. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 14:34 ET (operator: "Create ticket for each step and prove it to me that it works start with step 1").

Type: task, with a proof. Status: open. Blocked by: none.

## Question

Does the engine do this, and can each part be shown to work?

## The approved step

Every decision is recorded with the rule and mastering policy version that made it, the source records and identifiers it used, and its outcome, so any golden record, and any value it shows, can be explained from its source records.

(CONTEXT.md, "Mastering", approved by the operator one step at a time, 2026-11-09.)

## Where it lives today (from reading `edgar_warehouse/mastering/merge.py`, 2026-11-09 14:34 ET)

`add_decision` records only merges. On the shared store: 9 decisions against 461,455 golden records and 1,316,643 source records (counts, 2026-11-09). Joins and creations leave no decision. The rules version on mastering records is not recorded (ticket 199's open part).

## Checklist

- [x] Record a decision for every join and every creation, with rule, policy version, source records, identifiers and outcome. DONE (2026-11-09 22:50 ET): every bind by an identifier rule, a name rule or an exact-name rule (a join or a creation) is stored in `mastering_decision` as operation `bind` (`store.add_binds`, `merge._bind_decision`): rule id and version, the policy digest, the source record's assertion id, the golden record and the reason; the id leaves out the policy digest so a replay writes nothing twice. This also records the rules version on mastering decisions (ticket 199's open part). Read a bind as the decision at its time: a later merge moves the record, and `mastering_record.entity_id` holds where it is now.
- [x] Prove one golden record can be explained from its source records through its decisions (a test, then one real example in chat). DONE (2026-11-09 22:50 ET): `tests/storage_adapters/test_mastering_decisions.py::test_every_bind_by_an_identifier_rule_or_a_name_rule_is_recorded_with_what_it_used` (PostgreSQL 16 and MySQL, 3 passed; failed 3 of 3 on the old code, the bind decisions were absent): a golden record's source records are exactly the subjects its decisions bind to it, each naming its rule, version and the record used; a creation by the Form 4 issuer-and-symbol rule is recorded and a replay writes nothing twice. One real example in chat still to show after a load.
- [x] Prove a surviving value can be traced to the source record that supplied it. DONE (2026-11-09 22:50 ET): `test_a_surviving_value_traces_to_the_source_record_that_supplied_it`: the winning name's assertion id is named by a decision of its golden record, and the winner states its source and record key.
- [ ] Count decisions against golden records on the store after a load: none unexplained. DEFERRED to the ticket 201 go-live (2026-11-09 22:50 ET): the shared store's existing 1,316,643 source records were bound before bind decisions were recorded, so the count is meaningful only after the empty-start loads; each source's `mdm reconcile` then pairs with the decision count (one bind decision per bound record). FIRST SOURCE (2026-11-10 00:27 ET): on `local-staging` after the SEC company load, 5,091 records stored, 5,091 with a golden record and 5,091 bind decisions, one per record, none unexplained. The other sources repeat the count as each loads. (2026-11-10 05:12 ET) After SEC company, N-PORT registrant, Form ADV, SEC person and N-PORT fund: 71,283 records, 71,230 with a golden record, 70,821 distinct bound subjects and 70,821 subjects with a bind decision, one for one; the 409 extra records are custodians restated in both months (one subject, one decision), and the 53 records without a golden record all wait with an open review. None unexplained.
- [x] Learning → skill: name the skill line this ticket changed, or write "none". DONE (2026-11-09 22:50 ET): none.
