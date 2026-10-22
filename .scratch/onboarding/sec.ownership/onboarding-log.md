# Onboarding log: SEC insider ownership (Forms 3, 4 and 5), the reporting owner

Skill: data-onboarding. Profiling ticket 07 (rebuild-priorities 01), branch
`claude/ownership-contracts`. Every count here comes from the local copies
(`~/.local/share/edgartools/clean-mdm/proving/p07`, 8,723 filings); no request
left the machine. Names stay out of this file (the repo is public).

## discover, plan-parts

- Approved findings: `.scratch/profiling/trials/readers/ownership/cohort/findings.yaml`
  (operator, 2026-10-12, "approved"): the issuer is the existing Company (by CIK);
  the reporting owner is master data, a Person or Company (by CIK); the owner on a
  filing is a relationship onboarded with both masters.
- Source extracts: `ownership-xml.yaml` and `ownership-sgml.yaml` (#951, approved
  digests). This change adds two columns to their owner table (below).
- Parts, in order: the owner (this log); the transaction and holding tables to
  silver (later, their silver specs).

## Questions and answers

1. Does the ownership feed create owner records of its own, or only link to owners
   mastered from submissions? Operator, 2026-10-13 20:30 ET: "Create its own
   (Recommended)".
2. The 170 "see remarks" officer titles. Operator, 2026-10-13 20:30 ET: "Keep them
   apart (Recommended)": the title stays as filed; the remarks are their own column.
3. A Form 4 does not say whether the owner is a person or a company. Which owners
   does the first contract master? Operator, 2026-10-13: "Persons by role first
   (Recommended)": a person-shaped name the filing names a director or officer;
   every other owner held back, non-blocking, for a second step.
4. The 31 person verdicts the proven rule left undecided (their submissions documents
   carry company-style fields), drafted as people. Operator, 2026-10-14 (recorded
   07:00 ET): "All 31 are people (Recommended)". Their CIKs stay outside the repo
   (`proving/ownership/operator-checked-persons.json`); `measure.py` takes the file.
5. The Proving Run stopped: the Merge Stage closure followed the links into one group
   of more than 10,000 records. Operator, 2026-10-14: "Fix the Merge Stage
   (Recommended)", then "merge stage should have no limt". A separate ticket.

6. A ten-percent owner: `BENEFICIAL_OWNER_OF`, or `CONTROLS` (where the older built-in type list puts
   `ten_percent_owner`)? Operator, 2026-10-14 08:19 ET: "BENEFICIAL_OWNER_OF (Recommended)": the SEC's own
   words (beneficial ownership of more than 10%); holding 10% is not control.
7. The 198 director or officer owners with no submissions document have no label, so the proof does not
   cover them. Operator, 2026-10-14 08:19 ET: "Check a sample first (Recommended)": a random 50, labelled from the
   filing alone, checked by the operator before the switch-on.

## identify

- Source `sec.ownership`, source code `sec.ownership.reporting_owner.v1`, bronze
  family `filing_artifact` (the SGML submission files; the cohort's bare primary
  documents sit under `filings/`). Not a new domain: kind `person`.

## map

- One record per reporting owner on one filing, keyed `(accession, rpt_owner_cik)`:
  each filing is its own record (mastering-to-done 02, D3), so its capacities are a
  dated sighting.
- The owner table now carries the filing's `issuer_cik` and `period_of_report`
  (`from: document`), so the contract can state the owner's link to the issuer,
  dated by the filing. Test: `tests/engine/test_ownership_readings.py`.
- Fields: `legal_name` from `rpt_owner_name`. The owner's address is never captured
  into MDM for a reporting owner (Person consumer spec).
- Identifier: `cik` (the owner's CIK), `sec_cik`. Added to the Person CIK
  Identifier Contract's sources.
- Links (every type already declared, `relationship-types-v3`):
  `EMPLOYED_BY` as `director` (held `is_director`) and as `officer` (held
  `is_officer`, title `officer_title`); `BENEFICIAL_OWNER_OF` as
  `ten_percent_owner` (held `is_ten_percent_owner`); each to the issuer's Company
  (`sec.submissions.company.v1`, the issuer's CIK), on the period of report.
  `isOther` and `otherText` are not a capacity of either type: left out.
- Kind rules (`rules/merge/kinds/person.yaml`, version `person-2026-10-13.1`):
  - `sec-ownership-person` (classification): `sec-person-candidate`'s name tests
    on `rpt_owner_name`, and a person only when the filing names the owner a
    director (step `3-director`) or an officer (step `3-officer`). Steps 1 and the
    structural-fields test are dropped: a Form 4 states no entity type and none of
    those fields.
  - `sec-ownership-person-cik` (binding on the CIK), shaped like `person-cik`.
  - `defaults.sources` gains the source after `sec.submissions.person.v1`.

## quality

- `quality.yaml`: `legal_name_present`, `exception`, as the Person feed.

## test

- Measured (`measure.py`, `measure.json`, counts only): 8,723 filings, 9,313 owner
  rows, 0 refused. The rule's label is `sec-person-candidate` run on the owner's own
  submissions document (all-76230), and the operator's check for the 31 it left
  undecided. Person verdicts: 4,820 owners; 4,622 labelled person, 198 with no
  submissions document; 0 labelled entity. By step: director 2,488 of 2,488, officer
  2,148 of 2,148. Adversarial: 363 owners labelled entity, 0 called a person.
- Before the role condition (the rule ported as it was): 39 owners the proven rule
  left undecided were called people, 6 of them entities (union bodies and
  investment vehicles), all six only ten-percent owners. The role condition is what
  keeps them out.
- Proving Run (`proving_run.py`, 2026-10-13 20:55-21:14 ET): stopped in the first
  pass, "Affected closure exceeds bounded replay budget". The closure follows links
  both ways (an owner pulls in its issuer, the issuer every other owner linking to
  it), so the cohort's insider network is one group: 8,272 owner records, 1,706
  issuers and their decisions, over 10,000. Waits for the Merge Stage ticket.

## Guesses and gaps

- The proof's labels are another rule's verdicts, not hand labels: a proven rule
  (720 hand-checked labels) run on richer evidence about the same CIK. The 31 it
  left undecided were drafted by an agent and checked by the operator (answer 4).
- A prolific owner: one record per filing. The Merge Stage closure limit is being
  removed (answer 5).

## The lines and owners to silver (rebuild priorities ticket 25, 2026-10-22)

- Rulings: "Agreed Remove HOLDS from MDM's relationship types", "Re-scope ticket 25
  to land Form 4 holdings in silver", "Don't we need a as of date for holdings",
  "Lines + owners, as SEC (Recommended)".
- The source's own shape: SEC's Insider Transactions Data Sets keep the four line
  tables (NONDERIV_TRANS, NONDERIV_HOLDING, DERIV_TRANS, DERIV_HOLDING) apart from
  REPORTINGOWNER, joined by accession. Silver does the same: `ownership_line` (the
  four tables in one, a column naming each) and `ownership_owner`.
- Measured on the 3,367 local filings (the cohort is bare XML, so no filing date
  is local: it comes from the SGML header in production): 3,326 filings name one
  owner, 41 several (7 two, 3 three, 31 four or more), holding 145 of the 11,451
  lines; every line has an as-of date and a 10-digit issuer CIK; every amount is
  a number (at most 9 integer digits); line D/I: 5,525 direct, 5,926 indirect; no
  line or owner key repeats.
- The owner's Person is found by its record key in
  `sec.ownership.reporting_owner.v1` (accession and CIK, as MDM writes a two-part
  key); an owner the ownership feed holds back is found as a Company by its CIK.
- Gaps: the Security link waits for ticket 24; no Bookkeeping step lands silver
  (ticket 79's gap, after #1121), so `silver land` lands the rows by hand.
