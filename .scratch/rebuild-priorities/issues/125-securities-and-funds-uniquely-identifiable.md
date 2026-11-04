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

## Plan for the open rule changes (2026-11-03 20:49 ET, from reading the configured files)

Three slices, each its own branch and PR, configuration first (no engine code), each approved under the standing approval with a test run on invented data:

1. **Fund for a filing with no series id** (the Fund kind, `rules/sources/sec.nport.fund/`): `source.yaml` stops dropping a blank series id (its `select`) and gives each filing a fund key (the series id, else the registrant's CIK, which the reading already joins as `cik`); `reduce.yaml` and `combine.yaml` group by that key; the Dataset Contract's `record_key`, `identifiers` and `cross_references` carry it; `rules/merge/kinds/fund_structure.yaml` gains one binding rule on the registrant CIK (as `nport-fund-series`) with its Identifier Contract, its `verification` from the test run's report, and `policy.yaml`'s `automatic_rules`; the two mapping workbooks are regenerated and the policy digests in `tests/mdm` follow.
2. **The Securities chain reads SEDOL and LoanX by label** (`rules/sources/sec.nport.security/`): `identifiers.yaml` (now only ISIN-shaped values) also yields the "other identifier" pairs by label (`rules/identifiers/sedol.yaml`, `loanx.yaml` already hold the types); `holding.yaml`, `reduce.yaml`, `record.yaml` and `combine.yaml` carry them; a Security with no CUSIP or ISIN is keyed by one; the Security kind gains the two binding rules and Identifier Contracts; Bloomberg ids and FIGIs stay cross-references.
3. **The LEI on the series GLEIF names** (`combine.yaml` of the Fund source): today a shared LEI joins no series (`lei_once`); the rule reads the GLEIF legal name for each shared LEI from GLEIF's run (the "read another run" lookup, ticket 120) and joins the LEI to the one series whose name it equals; a name that is the adviser's, trust's or company's joins none (3 of 15 in 2026 Q2).

## Checklist

GLEIF permission: operator, 2026-11-03, "agreed for ticket 125" (the Golden Copy download). It was not needed: the 2026-09-11 16:00 Golden Copy was already on disk.

- [x] Identifier types `sedol` and `loanx` (`rules/identifiers/`), measured on the captured 2026 Q2 holdings (2026-11-03 19:15 ET): SEDOL 195,695 rows, 26,012 distinct, 195,528 pass shape and check digit (new check-digit family `weighted sum 1 3 1 7 3 9 1 mod 10`, in the engine and in profiling; 67 fail the check, 40 the shape); LoanX 5,579 rows, 5,253 are `LX` and six digits, no check digit (326 another length); tests: `tests/mdm/test_clean_identifier_types.py`, `tests/unit/test_profiling_columns.py`; 1,272 tests in `tests/mdm` and `tests/unit` pass
- [ ] ~~Identifier type `cins`~~ not declared (2026-11-03 19:15 ET, found on the data): of 1,327 rows labelled CINS, 1,316 start with a digit (CUSIPs under the wrong label, 244 of them pass the CUSIP check digit) and only 11 start with a letter (8 pass). A CINS is a CUSIP with a country letter, the same length and check digit, so the `cusip` type already accepts it, and a second type with the same family and length made the quality plan ambiguous (`tests/unit/test_data_quality_plan.py` failed). The chain reads a CINS-labelled value as a CUSIP; to confirm with the operator
- [ ] The Securities chain reads them from N-PORT's "other identifier" by label, and keys a Security by one when it has no CUSIP or ISIN; Bloomberg ids and FIGIs as cross-references
- [ ] Identifier Contracts for the three, verified on a test run (no identifier on two Securities), approved under the standing approval
- [ ] Funds with no series id: check that each such filing is a single-fund registrant; key the Fund by the registrant's CIK, its LEI an identifier; a test run
  - [x] (2026-11-03 20:46 ET) Measured on the 2026 Q2 data set: 729 of 14,416 filings name no series id, from 703 registrants; every one of the 729 carries a registrant LEI; 679 registrants file once, 24 file two or three times and 23 of those use one name for all (one fund), one uses several names; 702 of the 703 registrants file nothing that names a series. So the registrant is the fund for 702 registrants; one registrant files both kinds and needs its own look
  - [ ] Key the Fund by the registrant's CIK for a filing with no series id, its LEI an identifier; a test run
- [x] (2026-11-03 20:46 ET) The shared LEIs checked against the GLEIF Golden Copy (2026-09-11 16:00; the local capture, no download: its links pointed at the folder before ticket 73 renamed it, and are repointed). The 2026 Q2 data set has 15 LEIs on two or more series (not 16). GLEIF names one series for 12 of them (its legal name is that series' name); for 3 it names the adviser, the trust or the company (one of them on 27 series), not any series
  - [ ] The matching rule keeps the LEI on the series GLEIF names, and keeps it as a filed value only on the others; the 3 LEIs GLEIF gives to the adviser, trust or company attach to no series; counts to the operator
- [x] (2026-11-03 20:46 ET) The one series with two LEIs: GLEIF gives one LEI the series' own fund name and the other a different fund's name, so the series keeps the first
  - [ ] The matching rule keeps the LEI GLEIF names for the series and the other as a filed value
- [ ] Learning → skill (`security-master`; a fund skill if one is made)
