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

## Step 1 for every source: the gaps and the rulings (2026-11-09 16:06 ET; operator: "Make sure every source follows step 1 no excuses")

Counts on the shared store, records with no golden record, by source and reason (counts only):

| Source | Records | Why | Ruling and fix |
|---|---|---|---|
| SEC company and SEC submissions person (the same filers) | about 38,700 filers | The company classification takes only the types operating and investment; the person rule takes only person-shaped names; a filer of type other with a company name matches neither | Operator: "1 agreed": an SEC filer that is not a person becomes a Company by default; a person only when the name shape proves it. To build: the Company classification rule, tested on invented records, then on real counts |
| Form 4 security | 889 | The ticker rule creates nothing | Operator: create by issuer CIK and title (above) |
| Form ADV custodians named only by name | 1,429 | The exact-name rule waits | Operator: by name, with name plus place for names without a legal form (parts 3 to 5 above); part 3 merged (PRs 1565, 1566) |
| GLEIF | 21,589 | GLEIF never creates a Company | Operator: "2 no gleif is a secondary source". A secondary source attaches to golden records other sources create and never creates one; its records wait with a recorded review. This is the one stated exception to "every record has a golden record" |
| OpenFIGI "not found" | 30,121 CUSIPs and 7,560 ISINs | The provider returned nothing, and the record is set aside | Operator: "3 openfigi is currently creating only equity so if it is equity then yes if not no". Measured: 30,117 of the 30,121 CUSIPs are already held by Security golden records made from 13F and N-PORT, so the not-found record attaches to that Security and records that OpenFIGI does not know it; 4 CUSIPs are held by none and carry no security type, so by the ruling they create nothing. The 7,560 ISIN-only records are not yet measured |
| Records with an invalid check digit (LEI or CUSIP) | 34 + 14 + 2,429 + 1 | The whole record is set aside for one bad identifier | The record masters by its other identifiers or its name and the bad value is kept as flagged evidence (proposed; not yet ruled) |
| Form 4 reporting owners | 781 | Person or company undecided | Same ruling as the SEC filers |
| Missing record identity | 98 | No usable key | To look at |
| Form ADV filings v2 and N-PORT security | 12 and 6 | Not yet looked at | To look at |

Checklist for this section:

- [ ] SEC filers: the Company classification default, built and tested (2026-11-09 16:31 ET; operator: "1 agreed", then "I label it, you check it (Recommended)" for the proof sample). Found by reading `rules/merge/kinds/company.yaml` (`sec-company-candidate`, version 2026-09-25.13): step 8 takes operating filers, step 10 takes type other with an industry code, a category and a legal-form word, step 9 defers person-suffixed names, and step 11 sets aside everything else (67,166 of the 69,816 set-aside records). Steps 1 to 7b are deliberate set-asides for other entity types (asset-backed issuers 1,062, funds and governments about 254, held-back shells 599) and stay. Making step 11 a Company would double-master the 31,097 individuals the person rule takes as Persons, so the default must first defer person-shaped names with the person rule's own test. A changed classification rule is switched on only by a measured proof (`rules/merge/policy.yaml`: Wilson lower bound per step, an adversarial fixture and a cohort). Parts:
  - [ ] Rule: a step before the default that defers person-shaped names (the person rule's name-shape test), a step for type other with a legal-form word and no industry code or category, then the default as a Company; new rule version.
  - [ ] Measure through the engine: how many of the 67,166 become Companies, how many stay deferred as person-shaped, none double-mastered (counts only).
  - [ ] Proof: a random sample of the newly classified filers per new step, labelled by evidence (legal-form word, industry code, tickers, name shape), the whole table shown to the operator; the adversarial fixture and cohort hashes refreshed; the Wilson bound recomputed.
  - [ ] Approval line for the merge policy digest under "Approved the rules always", then reload the SEC company source so the new Companies exist; count before and after.
- [ ] OpenFIGI not found: attach the record to the Security that holds its CUSIP and record the answer; count the 7,560 ISIN-only records the same way.
- [ ] Records with an invalid check digit master by their other identifiers or name; the operator's word on the proposal.
- [ ] Form 4 reporting owners follow the SEC filer ruling.
- [ ] Look at the 98 missing-identity records, the 12 Form ADV filings v2 and the 6 N-PORT securities.
- [ ] Name "secondary source" in `CONTEXT.md` once the operator agrees the definition: a source that attaches to golden records others create and never creates one.

## Checklist

- [ ] Show that no code path writes a golden record except `mastering.merge`: list every writer of the master tables and name each caller (read the code, then test it).
- [ ] Show every source's records are accounted for: per source, records in = joined + created + waiting + set aside, counts only, on the store.
- [ ] Name each identifier that is kept in the cross-reference table but never searched, and the ticket that changes it.
- [ ] A test per source kind that a record of that source reaches `mastering.merge`, one test per kind.
- [x] Decided the 1,429 Form ADV custodians named only by name (2026-11-09 14:56 ET; operator: "master using name and company type if company type does not exist provide me option", then "Name plus place (Recommended)"). They are mastered as Companies by the exact name with its legal form kept. Measured, counts only: 961 distinct names, 559 end in a legal form and 402 do not; none carries an identifier. A name with no legal form uses the custodian's city, state and country with the name; a name with no place waits for a data steward with a recorded exception. Evidence first: the rule is declared, tested in both source orders and approved on that evidence before it is switched on.
- [ ] Write the custodian name-and-place rule in a copy of the policy; test both source orders, a second pass, a name shared by two places and a name with no place; then activate. Plan (2026-11-09 15:32 ET): (1) PR 1563 (merged) lets an exact-name rule create (`on_no_match: mint`). (2) The rule must name which cross-reference it keys on, so one rule joins by name for every custodian (as today, `wait`) and a second creates only for names that end in a legal form (a `name_form_id` cross reference, built with `regex_extract` in `custody-csv.yaml`, null for the others). (3) Names without a legal form use a name-plus-place cross reference; this needs the name and the city, state and country joined into one text, which the mapping language has no operation for, so it is a small addition to the mapping language or to the `name_id@1` format. (4) Custodians are keyed by `custodian_id` (`name:<NAME>`) in the MDM table, the silver facts and the adviser links; a place in that key for bare names touches all three (8 files with the tests). (5) Test on invented records, then the limited test on the real counts, record approval, activate.
- [ ] The legal-form list, for the operator to approve (2026-11-09 15:32 ET). Strict list, legal forms only: LLC, L.L.C., LP, L.P., LLP, LLLP, PLLC, PC, INC, INCORPORATED, CORP, CORPORATION, CO, COMPANY, LTD, LIMITED, PLC, N.A., NA, SA, S.A., AG, GMBH, BV, NV (a name ends in one). Counts, correcting the 559 and 402 above, which used a looser list that also counted TRUST, BANK and SECURITIES: 961 distinct waiting names, 449 end in a strict legal form, 512 do not. Open question for the operator: do TRUST and BANK count as a company type on their own (about 110 more names by name alone), or do they use name plus place (recommended)?
- [ ] The 780 ownership securities with no golden record: the operator's ruling (2026-11-09 15:59 ET; "This is not following step 1" on a Form 4 security stored without a golden record; then "Create by issuer and title (Recommended)"): when no Security holds the Form 4's ticker, mastering creates a Security golden record identified by the issuer's CIK plus the security title; ticker alone is not used. To build: a key made from the issuer CIK and the title, an exact-name rule that creates by it, tests on invented records (the Form 4 security has a golden record; two titles of one issuer are two Securities; a later OpenFIGI record joins it, with duplicates resolved by step 4), then the limited test on real counts. The conformance test for it is written with the rule, so it does not stay red on `main`.
- [ ] Explain the 2,046 records delivered but not stored.
- [ ] The person on a Company golden record (operator, 2026-11-09 14:56 ET: "repair, if needed delete and re-run"; Option 1, two golden records never joined across entity types): the join is fixed for new records (PR 1560, `test_an_individual_with_the_cik_of_a_company_gets_its_own_person_golden_record`). Repair the one existing golden record: remove the person's record from the Company golden record and master it again as a Person, then count it.
- [ ] Prove an undecidable record waits and creates no golden record, for each source whose entity type a rule decides (SEC company, SEC person, Form 4 reporting owner): a test with one such record, counting golden records before and after, and its recorded reason (moved here from ticket 205, 2026-11-09 17:41 ET; operator: step 1 mastering).
- [ ] Source onboarding declares each source's entity type (operator, 2026-11-09 17:41 ET: "This needs to be stored in a table and a YAML with mapping document filled in by the data onboarding skill this is not step 2 this is step 0"): a block in each source's YAML (fixed type, or decided by classification rule and the types it can give), a queryable entity type and origin per registered source, a row in the Mapping Document, and a required part in the data onboarding skill; a registration check fails a source with none. Starting content: the 14-source table (6 sources state a fixed Security, Fund Structure or Company type; GLEIF Level 1 states it in its own category field; the SEC company, SEC person and Form 4 reporting owner sources are decided by a classification rule).
- [ ] Prove a name binds only on exactly one golden record (moved here from ticket 206, 2026-11-09 17:42 ET; operator: step 1): for each name rule, a name that one golden record holds joins it; a name that two golden records hold goes to review and joins neither; a name that none holds creates one or waits, as the entity type's creation rule says. This is the Name Matching work of ticket 202: the GLEIF name rules search the golden records for the name, former name and place and bind only on exactly one, with no separate count job. Waiting on the operator's word in ticket 202: when a later load makes a bound name shared, does the earlier binding stay?
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
