# Measure how far name-only Person sources can be bound deterministically

Type: research
Status: resolved
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

## Answer

Partially measured 2026-09-19; findings in
[`research/01-name-only-source-overlap.md`](../research/01-name-only-source-overlap.md).
Prod Snowflake is suspended ("free trial has ended"), and the S3 landing
prefix is empty, so `sec_ownership_reporting_owner` was unreachable; the
name-only sources were measured from the latest full-snapshot S3 exports.

- Proxy `exec_name` is 47% role text — a parser defect
  (ticket 10), not a matching question. Proxy cannot bind until fixed.
- 8-K names are 97.7% clean; `(issuer CIK, normalized name)` is the only
  deterministic key; 398 of 10,042 plausible names appear under more than
  one issuer, so a name never binds alone or across issuers.
- Reporting-owner-side questions (1 and 3) remain unmeasured → ticket 09.

Ticket 02 is unblocked on these facts: the reporting-owner numbers would
refine a binding rule's expected hit rate, not change which evidence is
allowed to bind.
