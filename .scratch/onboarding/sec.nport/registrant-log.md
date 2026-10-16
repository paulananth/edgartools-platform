# N-PORT part 2: the registrant as a Company (ticket 79)

The part's own log (part 1's is `onboarding-log.md` on its branch). Findings: `profiling/sec.nport-2026q2-final/findings.yaml`, approved 2026-10-15 06:29 ET, part `REGISTRANT.CIK` (master by CIK, confidence 1.0: 1,947 registrants over 14,416 filings).

## Does the registrant's CIK already make a Company? (2026-10-15 21:20 ET, explored)

Checked against the captures on this machine, no request: the SEC filer capture (`captures/sec.submissions.company/all-76230`, every SEC filer in bronze, 76,230 CIKs, 2026-09-28) and the ticker list (`company-catalog-dictionary-20261005`).
- All 1,947 registrant CIKs are SEC filers (none missing); 384 are in the ticker list.
- SEC's own entity type: 1,251 "investment", 688 "other", 8 "operating"; 1,925 have no SIC code and no category.
- The Company classification rule (`sec-company-candidate`): "investment" reaches no step but "set aside"; "other" needs both a SIC code and a category (none has a category); at most the 2 "operating" filers with a SIC code become Companies. So about 1,945 would never exist as Companies.
- Operator, asked whether the N-PORT registrant creates the Company when its CIK is not one yet (recommended: yes): **"agreed"** (2026-10-15).

## Configuration (configuration only)

`rules/sources/sec.nport.registrant/`: `submissions.yaml` (SUBMISSION.tsv: each filing's date as sortable text, a pair set), `source.yaml` (REGISTRANT.tsv, one row per filing with its date; the Dataset Contract `sec.nport.registrant.v1`), `reduce.yaml` (each CIK), `combine.yaml` (each CIK's latest filing kept whole, by date then accession). Company rules: `nport-registrant-cik` (binding, creates when none holds the CIK), declared not switched on; the CIK Identifier Contract's sources and `defaults.sources` gain `sec.nport.registrant.v1`, last, so every field another source fills wins. Lookup only: the SEC file number (`sec_file_number`) and the stated LEI (`nport_lei`). Left out: the phone number (personal). Mapping Documents regenerated.

## The one test run (2026-10-15 21:34 ET, tested locally)

`registrant_test_run.py`, report `registrant-test-run.json` (counts only), 23 s. Run twice: the first showed no filing date in sortable form (`regex_replace` replaces literally, no capture groups); fixed by cutting year, month and day apart and joining them with `concat`.
- 14,416 filings, every one with its filing date; 1,947 registrants (847 with several filings in the quarter).
- The latest filing chosen matches a direct calculation for 1,947 of 1,947; 18 registrants changed name and 31 changed address within the quarter (each Company carries its latest).
- `sec.nport.registrant.v1`: **1,947 accepted**, none set aside; name and address 1,947; CIK 1,947; file number 1,947; LEI 1,943 (4 all-zero stand-ins blank).
- Rules tests 124 pass; the 43 MDM tests that load the merge rules pass.

Next: the one Proving Run (after part 1's ends, one database at a time); then the approval under the operator's standing words, "Approved the rules always".

## The one Proving Run (2026-10-15 22:38-22:39 ET, tested locally)

`registrant_proving_run.py`, report `registrant-proving-run.json` (sha256 e217bf4d...da61, counts only); disposable PostgreSQL 16, container removed. `nport-registrant-cik` switched on only in the run's copy of the policy, stamped "proving-run". The cm27 SEC Companies (6,726) holding a registrant CIK went in first: 20 of them.
- First pass 34 s, 6 batches: **1,947 Companies, one per registrant CIK**; 1,947 bind decisions; **0 CIKs on two Companies**.
- **Second pass (5 s) changed nothing.**
- The 20 SEC records holding a registrant CIK were set aside by SEC's own Company classification (`classification_deferred`, as the CIK research foretold: investment filers reach no step but "set aside"), each an open review. So no registrant met an existing Company here: each created its own, and joining an existing SEC Company by CIK was not exercised in this run. The same rule shape (identifier match, cardinality, create when none) joined 10,278 Securities across 13F and N-PORT in part 1's Proving Run. If an SEC record for one of these CIKs is later classified a Company, it joins the N-PORT Company through `company-cik`.

## Approval (2026-10-15 22:44 ET)

- Operator's standing words, **"Approved the rules always"** (2026-10-15 18:56 ET), on the test run above and this Proving Run: approved the Dataset Contract `sec.nport.registrant.v1` and its source extracts; the matching rule `nport-registrant-cik` (version 2026-10-15.1, declared); `sec.nport.registrant.v1` added last to the CIK Identifier Contract's sources and to the Company's `defaults.sources`. No quality file: profiling found no defect for a check.
- Not covered by those words: **switching on** `nport-registrant-cik` (and the CIK contract's verification with this source), and the merge of PR #1001. Each waits for the operator.
