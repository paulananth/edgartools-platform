# 125: Securities and funds uniquely identifiable

Priority: 125 (operator, 2026-10-20 08:24 ET: "Securities and funds must be
uniquely identifiable"). Map: [Rebuild priorities](../map.md). Rules in the
`security-master` skill.

Type: task. Status: open. Blocked by: ticket 120 (the one Securities target).

## Measured (2026 Q2 N-PORT data set, captured; 2026-10-20)

- Holdings, 5,347,869: CUSIP 3,546,715; ISIN without CUSIP 812,952; a ticker
  only 59,409 (futures 14,711, forwards 14,125, options 10,605, loans 10,183,
  equities 5,530); only another identifier 928,791, of which the fund's own
  label 909,030 (loans 652,058, forwards 121,403, swaps 65,522) and a
  standard identifier 20,129 (Bloomberg 10,411, LoanX 4,616, SEDOL 1,876,
  CINS 1,226, FIGI 4, other labels 1,996); no identifier 2.
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

- [ ] Identifier types `sedol`, `cins`, `loanx` (`rules/identifiers/`), each with its shape and check digit where one exists; measured on the captured holdings
- [ ] The Securities chain reads them from N-PORT's "other identifier" by label, and keys a Security by one when it has no CUSIP or ISIN; Bloomberg ids and FIGIs as cross-references
- [ ] Identifier Contracts for the three, verified on a test run (no identifier on two Securities), approved under the standing approval
- [ ] Funds with no series id: check that each such filing is a single-fund registrant; key the Fund by the registrant's CIK, its LEI an identifier; a test run
- [ ] The 16 shared LEIs checked against the captured GLEIF Golden Copy; the matching rule keeps the LEI on the series GLEIF names; counts to the operator
- [ ] The one series with two LEIs: the same check
- [ ] Learning → skill (`security-master`; a fund skill if one is made)
