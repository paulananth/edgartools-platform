# The Company source extract keeps only what combine uses from filings

Status: claimed (Claude, branch `claude/company-extract-forms-only`, 2026-10-13 18:04 ET)
Blocked by: none

The operator, 2026-10-13: "Are there any more stupid design decisions that is costing us dearly", then "Yes" to fixing this one first. Measured on one bundle (960 captured documents, 129 MB): the Company source extract (`census-main.yaml`) writes 785,023 filing rows with 20 columns, 364 MB, and the verifier, the Bookkeeping engine's hash and combine each read it again. Combine's `forms` group is the only reader: it collects each CIK's distinct `form` values, checked against the capture run (`sync_run_id`).

- [x] The filings table keeps `form`, `cik` and `sync_run_id` only (the parallel fields: the anchor and `form`): census-main.yaml only loses lines (2026-10-13 18:51 ET)
- [x] Equivalence over the 7,000 captured documents of cm05: 0 refusals differ, 0 company or address rows differ, 0 CIKs whose distinct forms or capture run differ; 3,881,216 filing rows either way; filings 1,795 MB before, 204 MB after; time 201 s before, 58 s after (2026-10-13 18:51 ET); rerun on the final file after the review: the same, 208 s before, 58 s after (2026-10-13 19:02 ET)
- [x] Affected tests: test_company_census_configuration (the copy check now allows the narrowed filings and checks the kept columns equal the source's) and test_clean_company_preparation, 30 pass; the installed-bundle tests build from the commit and need Docker, so CI runs them (2026-10-13 18:51 ET)
- [x] Review, three axes (2026-10-13 18:54 ET): GoF leave it (the copy check gains one narrowed-table exception; a generated copy would split what is approved, revisit at a sixth divergence). Standards: no hard violations; stale header, sizing comment in company_prepare.py and test docstring fixed. Spec: nothing wrong; the unused anchor field `accession_number` dropped too (same output on 300 of 300 documents). On purpose: the 17 dropped fields are no longer shape-checked, so a document whose dropped fields have the wrong shape is now accepted; length mismatches never refused (`lengths: anchor`) and their values never did (`on_invalid`)
- [ ] The `census-main.yaml` digest explained and approved by the operator
- [ ] The Company installed proof rerun: the same outcomes, and its time beside the last run's 42.1 min
- [ ] PR, CI green, merge on the operator's word

Next, after this: the decision on verifiers that rerun the whole step (finding 1), the second parse for the keys extract (finding 4, held by the census lookup's 64 MB and 100,000-row bounds), and preparation's sizing read (finding 5).
