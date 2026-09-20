# Measure how far name-only Person sources can be bound deterministically

Type: research
Status: open
Blocked by: none

## Question

Two of four Person sources carry no identifier: `sec_executive_record`
(DEF 14A, `exec_name` + role + issuer `cik` + fiscal year) and
`sec_employment_event` (8-K Item 5.02, `person_name` + role + issuer `cik` +
date). The decision on what may bind them (ticket 02) needs facts, not
guesses:

1. For each name-only row, does a `sec_ownership_reporting_owner` row exist
   with the same issuer CIK, a normalized-equal name, and an `is_officer` /
   `is_director` flag consistent with the role? What fraction of proxy and
   8-K rows have exactly one such candidate, more than one, or none?
2. How often does one normalized name appear under *different* issuers
   with different `owner_cik`s (the "same name, different person" rate)?
3. How many distinct `owner_cik` values are natural persons versus entities
   (10% owners that are funds/companies), by flag combination?

Read-only against `EDGARTOOLS_SILVER` in prod (the only silver store), or
against a frozen extract. Record the query, the run identity, row counts,
and SHA-256 of the result set, the way
`.scratch/gleif-company-augmentation/research/01-*` did. **Needs operator
go-ahead before running against prod.**
