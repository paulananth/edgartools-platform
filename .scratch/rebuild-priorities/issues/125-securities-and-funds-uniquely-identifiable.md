# 125: Securities and funds uniquely identifiable

Priority: 125 (operator, 2026-10-20 08:24 ET: "Securities and funds must be
uniquely identifiable"). Map: [Rebuild priorities](../map.md). Rules in the
`security-master` skill.

Type: task. Status: in progress (2026-11-03 19:15 ET, Claude; part 1 done). Blocked by: ticket 120 (the one Securities target).

## Measured (2026 Q2 N-PORT data set, captured; 2026-10-20)

- Holdings, 5,347,869: CUSIP 3,546,715; ISIN without CUSIP 812,952; a ticker
  only 59,409 (futures 14,711, forwards 14,125, options 10,605, loans 10,183,
  equities 5,530); only another identifier 928,791, of which the fund's own
  label 909,030 (loans 652,058, forwards 121,403, swaps 65,522), a label
  "client" 1,628 (the fund's own too), and a standard identifier 18,133
  (Bloomberg 10,411, LoanX 4,616, SEDOL 1,876, CINS 1,226, FIGI 4); no
  identifier 2. (First reported to the operator as 20,129 standard
  identifiers: a sum error, corrected the same day.)
- Funds: 14,416 filings, 12,944 series; 729 filings with no series id (held
  back, `missing_record_identity`); 16 LEIs filed on two or more series; one
  series filed with two LEIs.

## Rulings (operator, 2026-10-20 08:28 ET)

- A holding with only the fund's own identifier: "Not Securities
  (Recommended)": it stays a holding under its fund.
- Standard identifiers in the "other" field: "SEDOL, CINS, LoanX
  (Recommended)": identifiers that create and join Securities, each with its
  Identifier Contract; Bloomberg ids and FIGIs cross-references only.
- A fund filed with no series id: "Registrant's CIK and LEI (Recommended)":
  the fund is the registrant; check on the data first.
- An LEI on several series: "Check against GLEIF (Recommended)": the series
  GLEIF names keeps it as an identifier; the others keep it as a filed
  cross-reference.

## Checklist

- [x] Identifier types `sedol` and `loanx` (`rules/identifiers/`), measured on the captured 2026 Q2 holdings (2026-11-03 19:15 ET): SEDOL 195,695 rows, 26,012 distinct, 195,528 pass shape and check digit (new check-digit family `weighted sum 1 3 1 7 3 9 1 mod 10`, in the engine and in profiling; 67 fail the check, 40 the shape); LoanX 5,579 rows, 5,253 are `LX` and six digits, no check digit (326 another length); tests: `tests/mdm/test_clean_identifier_types.py`, `tests/unit/test_profiling_columns.py`; 1,272 tests in `tests/mdm` and `tests/unit` pass
- [ ] ~~Identifier type `cins`~~ not declared (2026-11-03 19:15 ET, found on the data): of 1,327 rows labelled CINS, 1,316 start with a digit (CUSIPs under the wrong label, 244 of them pass the CUSIP check digit) and only 11 start with a letter (8 pass). A CINS is a CUSIP with a country letter, the same length and check digit, so the `cusip` type already accepts it, and a second type with the same family and length made the quality plan ambiguous (`tests/unit/test_data_quality_plan.py` failed). The chain reads a CINS-labelled value as a CUSIP; to confirm with the operator
- [ ] The Securities chain reads them from N-PORT's "other identifier" by label, and keys a Security by one when it has no CUSIP or ISIN; Bloomberg ids and FIGIs as cross-references
- [ ] Identifier Contracts for the three, verified on a test run (no identifier on two Securities), approved under the standing approval
- [ ] Funds with no series id: check that each such filing is a single-fund registrant; key the Fund by the registrant's CIK, its LEI an identifier; a test run
- [ ] The 16 shared LEIs checked against the captured GLEIF Golden Copy; the matching rule keeps the LEI on the series GLEIF names; counts to the operator
- [ ] The one series with two LEIs: the same check
- [ ] Learning → skill (`security-master`; a fund skill if one is made)
