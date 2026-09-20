# Capture the reporting-owner evidence the Person contract needs, from bronze

Type: task
Status: open
Blocked by: none

## Question

Nothing to decide. Graduated from the map's fog by ticket 04, which fixed
the field set and so fixed what the parser must keep. Three changes to
`edgar_warehouse/parsers/ownership.py` and its silver columns, all in the
same area, for whoever owns `edgar_warehouse/parsers/`:

1. **Keep `otherText` and per-owner footnote text.** Ticket 03's rule C-J
   treats deputization language as evidence; research 18 read it from
   bronze because silver does not carry it. Today
   `sec_ownership_reporting_owner` has `is_other` but not its text
   (`edgar_warehouse/silver_schema.py:422-435`).
2. **Classify from the bronze `submissions.json`, not a live SEC fetch.**
   `Ownership.from_xml` fetches every reporting owner's submissions live at
   parse time (edgartools 5.30.0 `ownershipforms.py:1017-1020`) and computes
   an `is_company` the repo discards. Rule C-J needs `entityType`, `sic`,
   `stateOfIncorporation`, `ein`, `tickers`, `ownerOrg`, `fiscalYearEnd`
   for each owner CIK — all present in bronze for 4,831/4,831 owner CIKs
   measured (research 18). Feed bronze; make zero SEC requests.
3. **Reduce the owner address to two booleans and drop the rest.** Ticket 04
   Q4: no street/city/state/zip may enter silver, an assertion, or a
   projection. Keep only `address_is_care_of` and `address_non_us` as
   classification evidence; bronze retains the raw artifact unchanged.

Production parser code: its own branch, the mandatory
`/gof-refactor-reviewer` consult, the three-axis `/code-review`. Note
research 12 F8 — the per-filing fetch has no `--force`, so a parser change
alone does not re-parse already-marked accessions. Sibling of
[ticket 10](10-fix-proxy-executive-name-parser-leak.md); the two touch
different parsers and can land independently.

Resolved when the three fields/behaviours are present in a re-exported
silver sample and rule C-J can be evaluated without any SEC request.
