# 205: Step 2: one entity type per source record

Priority: 205. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 14:34 ET (operator: "Create ticket for each step and prove it to me that it works start with step 1").

Type: task, with a proof. Status: resolved. Blocked by: none.

## Question

Does the engine do this, and can each part be shown to work?

## The approved step

Each source record has exactly one entity type: the source's own where it states one, otherwise decided by classification rules. A record whose entity type cannot be decided waits, and no golden record is created for it. Other things the record mentions are relationships to other golden records, resolved when those golden records exist.

(CONTEXT.md, "Mastering", approved by the operator one step at a time, 2026-11-09.)

## Where it lives today (from reading `edgar_warehouse/mastering/merge.py`, 2026-11-09 14:34 ET)

The merge runs per kind (`Settings.kind`). `set_aside` keeps records no rule may master, with a review. Not verified: a classification rule that decides the type for a source that states none, and that an undecided record never creates a golden record.

## Checklist

- [x] Per source, name where its entity type comes from (the source states it, or a classification rule decides it). DONE (2026-11-09 21:42 ET): `files.entity_types` reads it for the 14 Dataset Contracts (10 fixed, 3 by a classification rule, 1 by the source's category field), `rules check` refuses a contract that states none (PR 1581), and the Rules Database view `rules.source_entity_type` lists it (PR 1584).
- [ ] ~~Prove an undecidable record waits and creates no golden record: a test with one such record, counting golden records before and after.~~ moved to ticket 204 (step 1) (2026-11-09 17:41 ET; operator: "This should be part of 'Pending: prove an undecidable record waits and creates no golden record.' step 1 mastering").
- [x] Prove a mentioned other party becomes a relationship, not a second golden record, and resolves when both exist (one test per relationship kind). Partly done (2026-11-09 21:42 ET): `tests/integration/test_mastering_relationships.py`, PostgreSQL 16, 9 passed: CUSTODIAN, RELATED_PERSON, IS_SUBFUND_OF, in capacities EMPLOYED_BY and BENEFICIAL_OWNER_OF, and with a GLEIF target SUCCESSOR_ENTITY, IS_DIRECTLY_CONSOLIDATED_BY, IS_ULTIMATELY_CONSOLIDATED_BY and ISSUED_BY each make the record's own golden record only (1 golden record, no link), then link when the mentioned party's own record is mastered (2 golden records of their own entity types). ALL NINE KINDS DONE (2026-11-09 22:11 ET).
  - [x] The kinds in capacities, EMPLOYED_BY and BENEFICIAL_OWNER_OF (a Person's dated sightings). DONE (2026-11-09 21:46 ET): added to the same test (a Person's sighting of the officer and ten-percent-owner capacities).
  - [x] The kinds whose target is a GLEIF record, ISSUED_BY, SUCCESSOR_ENTITY, IS_DIRECTLY_CONSOLIDATED_BY and IS_ULTIMATELY_CONSOLIDATED_BY: a mention creates no golden record, so the target exists only once a SEC or N-PORT Company holds its LEI (reworded 2026-11-10: no source is an exception to the six steps). DONE (2026-11-09 21:58 ET): `test_a_relationship_to_a_gleif_record_resolves_once_a_company_holds_its_lei`: a Company holds the LEI (a custodian record), the GLEIF record attaches to it and never creates one, and the link resolves once the target's Company and GLEIF record are mastered. FINDING: the GLEIF LEI rule `gleif-issuer-lei` is declared and not switched on in the repo policy, so the test switches it on in a copy; in the repo policy a GLEIF record attaches only through the name rules (tickets 202 and 203).
- [x] A record joins only golden records of its own entity type (2026-11-09 15:06 ET; operator: "Option 1"). Fixed in PR 1560 (`store.kinds`, filter in `_match_identifiers`). `test_an_individual_with_the_cik_of_a_company_gets_its_own_person_golden_record` failed before the fix (the Company's golden record came back typed `person`) and passes after; `test_a_fund_series_never_joins_a_company_or_person` guards it. PostgreSQL 16: 25 and 11 passed in the mastering and context tests; MySQL in CI.
- [x] The one existing wrong golden record repaired on the shared store (2026-11-09 15:06 ET; operator: "repair, if needed delete and re-run"). The individual's source record was removed from the Company golden record, which was rebuilt from its two Form ADV filings (all 7 registered policies reproduced it identically before the change), and the record was mastered again as a Person with the fixed code. After: 0 sources have records on more than one entity type; 1,316,643 source records (unchanged), 461,456 golden records (one more). Not done as a test: the repair ran as a one-off script, not through a load.
- [x] The N-PORT fund's registrant CIK (25,874 records) is stored and never used: resolve it as the fund's relationship to its registrant Company when that golden record exists. Found by ticket 204's list of keys stored and never searched, 2026-11-09 18:49 ET. DONE (2026-11-09 22:10 ET): already resolved. The fund's `IS_SUBFUND_OF` relationship reads its target from the same value (`latest.cik`, target source `sec.nport.registrant.v1`), and the step 2 test proves it links when both golden records exist (PR 1587). The `nport_registrant_cik` cross reference repeats that value and nothing searches it; removing it is a cleanup for the operator, not a gap.
- [x] Learning → skill: name the skill line this ticket changed, or write "none". DONE (2026-11-09 22:10 ET): `data-onboarding` test step: a source that states a relationship is shown to make no golden record for the mentioned party and to link once that party's own record is mastered.
