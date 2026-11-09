# 205: Step 2: one entity type per source record

Priority: 205. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 14:34 ET (operator: "Create ticket for each step and prove it to me that it works start with step 1").

Type: task, with a proof. Status: open. Blocked by: none.

## Question

Does the engine do this, and can each part be shown to work?

## The approved step

Each source record has exactly one entity type: the source's own where it states one, otherwise decided by classification rules. A record whose entity type cannot be decided waits, and no golden record is created for it. Other things the record mentions are relationships to other golden records, resolved when those golden records exist.

(CONTEXT.md, "Mastering", approved by the operator one step at a time, 2026-11-09.)

## Where it lives today (from reading `edgar_warehouse/mastering/merge.py`, 2026-11-09 14:34 ET)

The merge runs per kind (`Settings.kind`). `set_aside` keeps records no rule may master, with a review. Not verified: a classification rule that decides the type for a source that states none, and that an undecided record never creates a golden record.

## Checklist

- [ ] Per source, name where its entity type comes from (the source states it, or a classification rule decides it).
- [ ] Prove an undecidable record waits and creates no golden record: a test with one such record, counting golden records before and after.
- [ ] Prove a mentioned other party becomes a relationship, not a second golden record, and resolves when both exist (one test per relationship kind).
- [x] A record joins only golden records of its own entity type (2026-11-09 15:06 ET; operator: "Option 1"). Fixed in PR 1560 (`store.kinds`, filter in `_match_identifiers`). `test_an_individual_with_the_cik_of_a_company_gets_its_own_person_golden_record` failed before the fix (the Company's golden record came back typed `person`) and passes after; `test_a_fund_series_never_joins_a_company_or_person` guards it. PostgreSQL 16: 25 and 11 passed in the mastering and context tests; MySQL in CI.
- [x] The one existing wrong golden record repaired on the shared store (2026-11-09 15:06 ET; operator: "repair, if needed delete and re-run"). The individual's source record was removed from the Company golden record, which was rebuilt from its two Form ADV filings (all 7 registered policies reproduced it identically before the change), and the record was mastered again as a Person with the fixed code. After: 0 sources have records on more than one entity type; 1,316,643 source records (unchanged), 461,456 golden records (one more). Not done as a test: the repair ran as a one-off script, not through a load.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
