# 204: Step 1: every source record goes through mastering

Priority: 204. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 14:34 ET (operator: "Create ticket for each step and prove it to me that it works start with step 1").

Type: task, with a proof. Status: open. Blocked by: none.

## Question

Does the engine do this, and can each part be shown to work?

## The approved step

Every source record goes through mastering. It arrives with its source, its entity type, its identifiers, its fields, its relationships and its source time. Mastering decides which golden record it belongs to, or creates one. No source writes a golden record directly, and no identifier skips mastering.

(CONTEXT.md, "Mastering", approved by the operator one step at a time, 2026-11-09.)

## Where it lives today (from reading `edgar_warehouse/mastering/merge.py`, 2026-11-09 14:34 ET)

All 14 merge steps in `rules/sources` run `mastering.merge`. Some identifiers are kept in the cross-reference table and never searched (ticket 203), for example the N-PORT registrant LEI, which step 3 says mastering must search. The Form ADV, ownership and 13F mastering targets are incomplete (ticket 201).

## Measured on the shared store (2026-11-09 14:40 ET, read-only, counts and public names only)

- Only `store.write_masters` inserts into `mastering_master` (`store.py:219`); it is called only from `mastering/merge.py`, reached by the live worker and by `rebuild.py`. All 14 merge steps run `mastering.merge`. The old `mdm.*` record tables hold 0 rows.
- 1,316,643 source records stored; 0 point at a missing golden record. 1,314,434 are joined or created; 21,415 wait with an open review (21,294 `binding_required`, 121 `conflicting_identifiers`, counted by reason); 2,209 have no golden record and no open review (1,429 Form ADV custodians named only by name, 55 and 725 ownership securities of the two versions). 160,300 more are set aside in `mastering_deferred`.
- The files delivered 1,318,689 records and the store holds 1,316,643: 2,046 not explained (a restated record replacing its earlier version may account for it; not shown).
- By source and entity type, each of the 14 sources lands only in its own entity type, with one exception: one SEC submissions person record (an individual filer) sits on a Company golden record that also holds two Form ADV filings, joined by CIK. That is one record with two entity types, against step 2.
- Per-source, per-type tests do not exist yet.

## Checklist

- [ ] Show that no code path writes a golden record except `mastering.merge`: list every writer of the master tables and name each caller (read the code, then test it).
- [ ] Show every source's records are accounted for: per source, records in = joined + created + waiting + set aside, counts only, on the store.
- [ ] Name each identifier that is kept in the cross-reference table but never searched, and the ticket that changes it.
- [ ] A test per source kind that a record of that source reaches `mastering.merge`, one test per kind.
- [x] Decided the 1,429 Form ADV custodians named only by name (2026-11-09 14:56 ET; operator: "master using name and company type if company type does not exist provide me option", then "Name plus place (Recommended)"). They are mastered as Companies by the exact name with its legal form kept. Measured, counts only: 961 distinct names, 559 end in a legal form and 402 do not; none carries an identifier. A name with no legal form uses the custodian's city, state and country with the name; a name with no place waits for a data steward with a recorded exception. Evidence first: the rule is declared, tested in both source orders and approved on that evidence before it is switched on.
- [ ] Write the custodian name-and-place rule in a copy of the policy (name with legal form kept; with place when no legal form), test both source orders, a second pass, a name shared by two places and a name with no place; then activate.
- [ ] The 780 ownership securities with no golden record and no open review: why they wait, and what the Security creation rule says. Not covered by the custodian decision.
- [ ] Explain the 2,046 records delivered but not stored.
- [ ] The person on a Company golden record (operator, 2026-11-09 14:56 ET: "repair, if needed delete and re-run"; Option 1, two golden records never joined across entity types): the join is fixed for new records (PR 1560, `test_an_individual_with_the_cik_of_a_company_gets_its_own_person_golden_record`). Repair the one existing golden record: remove the person's record from the Company golden record and master it again as a Person, then count it.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
