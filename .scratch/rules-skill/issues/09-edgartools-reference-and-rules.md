# Research edgartools for reference data and rules beyond Company

Type: research
Status: resolved (2026-09-27 12:34 ET); recommendations await the operator
Blocked by: none

## Question

Operator, 2026-09-27: "check and reserch edgartools library to add any missing
config types and rules improve rules engin beond company".

1. What reference data and domain rules does edgartools (5.30.0, our PyPI
   dependency) carry: bundled files, lists and heuristics?
2. Which of them belong in `rules/`:
   - as reference tables;
   - as better sources for our hand-written lists;
   - as rule primitives?
3. What would the engine need for Person, Security, Fund and Adviser:
   - identifiers and their formats;
   - reference tables;
   - primitives;
   - the contract-language gaps the skill trials found?
4. What should come first, and at what cost?

## Checklist (times ET)

- [x] Research agent started (2026-09-27 05:03 ET). It reads source and
  bundled files only, with zero SEC requests. It writes
  [research 09](../research/09-edgartools-reference-and-rules.md).
- [x] Note written and reviewed (2026-09-27 12:34 ET).

## Answer

- **What edgartools ships:** 7 data files. Two matter:
  - `place_codes.csv`, already our place-code table (rules skill ticket 08);
  - `ct.pq`, 67,679 CUSIP-to-ticker pairs, all passing the CUSIP check
    digit. It suits a lookup-only Security table and CUSIP-format tests. It
    must never key a Security: 8,776 tickers map to more than one CUSIP.
- **What its code holds:** most of the value is lists and heuristics, not
  data files: a 9-signal individual-versus-company chain, SIC-based
  business categories, form sets, Form 4 transaction codes, and a BDC test
  by `814-` file number.
- **Our lists against its lists:** none of its lists beats ours. Candidates
  to *measure*:
  - `NPORT-EX` (fund-report forms);
  - `FOUNDATION`, `ASSOCIATION` and `NA` (legal forms);
  - `DR` and `ET AL` (person suffixes).

  Never add `MD`, `II`, `III` or `IV` as person suffixes.
- **What it does not have:** SIC, exchange (MIC) or legal-form tables, or a
  Form ADV parser. Its ISO country table has errors; do not use it.
- **Engine proposals:**
  - new identifier formats: CUSIP, ISIN, SEC series, SEC class, CRD, EIN,
    SEC file number;
  - four primitives: prefix, identifier-format, any-filled, reference-table
    lookup;
  - contract keys for the trial gaps: `none_values`, `lookup_identifiers`,
    `aliases`, `kind_from`, `publication:`.

**Recommended order, not decided:** `none_values`; `lookup_identifiers`; the
identifier formats; the CUSIP-ticker table; the measured list additions; the
`814-` BDC test; aliases; the individual-versus-company chain as candidate
Person rule steps; `publication:` and `kind_from`; form descriptions.
