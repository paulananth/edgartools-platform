# 125: Securities and funds uniquely identifiable

Priority: 125 (operator, 2026-10-20 08:24 ET: "Securities and funds must be
uniquely identifiable"). Map: [Rebuild priorities](../map.md). Rules in the
`security-master` skill.

Type: task. Status: resolved (2026-11-04 04:22 ET; the SEDOL and LoanX key moved to 190, the LEI on the series GLEIF names to 191). Blocked by: ticket 120 (the one Securities target).

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

1. **Fund for a filing with no series id**: found on reading `rules/sources/sec.nport.registrant/source.yaml` and `silver-holding.yaml`: every registrant, series or not, is already mastered as a Company by its CIK, and a holding of a filing with no series already links to that Company (`registrant_mdm_id`; ticket 79). A second master (a Fund keyed by the same CIK) would duplicate it, and the operator ruled the SEC registrant LEI lookup only on the Company. So this slice is a decision first: either the registrant Company is the fund for these 702 registrants (no build), or a second Dataset Contract makes a Fund per registrant (a new reading, rule, Identifier Contract and approval pins). Recommended: the Company is the fund.
2. **The Securities chain reads SEDOL and LoanX by label** (`rules/sources/sec.nport.security/`): `identifiers.yaml` (now only ISIN-shaped values) also yields the "other identifier" pairs by label (`rules/identifiers/sedol.yaml`, `loanx.yaml` already hold the types); `holding.yaml`, `reduce.yaml`, `record.yaml` and `combine.yaml` carry them; a Security with no CUSIP or ISIN is keyed by one; the Security kind gains the two binding rules and Identifier Contracts; Bloomberg ids and FIGIs stay cross-references.
3. **The LEI on the series GLEIF names** (`combine.yaml` of the Fund source): today a shared LEI joins no series (`lei_once`); the rule reads the GLEIF legal name for each shared LEI from GLEIF's run (the "read another run" lookup, ticket 120) and joins the LEI to the one series whose name it equals; a name that is the adviser's, trust's or company's joins none (3 of 15 in 2026 Q2).

## Checklist

GLEIF permission: operator, 2026-11-03, "agreed for ticket 125" (the Golden Copy download). It was not needed: the 2026-09-11 16:00 Golden Copy was already on disk.

- [x] Identifier types `sedol` and `loanx` (`rules/identifiers/`), measured on the captured 2026 Q2 holdings (2026-11-03 19:15 ET): SEDOL 195,695 rows, 26,012 distinct, 195,528 pass shape and check digit (new check-digit family `weighted sum 1 3 1 7 3 9 1 mod 10`, in the engine and in profiling; 67 fail the check, 40 the shape); LoanX 5,579 rows, 5,253 are `LX` and six digits, no check digit (326 another length); tests: `tests/mdm/test_clean_identifier_types.py`, `tests/unit/test_profiling_columns.py`; 1,272 tests in `tests/mdm` and `tests/unit` pass
- [ ] ~~Identifier type `cins`~~ not declared (2026-11-03 19:15 ET, found on the data): of 1,327 rows labelled CINS, 1,316 start with a digit (CUSIPs under the wrong label, 244 of them pass the CUSIP check digit) and only 11 start with a letter (8 pass). A CINS is a CUSIP with a country letter, the same length and check digit, so the `cusip` type already accepts it, and a second type with the same family and length made the quality plan ambiguous (`tests/unit/test_data_quality_plan.py` failed). The chain reads a CINS-labelled value as a CUSIP; to confirm with the operator
- [x] The Securities chain reads a SEDOL and a LoanX from N-PORT's "other identifier" by label and shape, and they join the Security their holding keys by its CUSIP or ISIN (`tests/integration/test_nport_sedol_loanx.py`, invented data: two SEDOLs on one CUSIP kept, a LoanX, an ISIN-keyed Security with a SEDOL, a holding with neither makes no Security; it failed before with `ValueError: Lookup document binds exactly declared sets to the input receipt`; the whole CI set passes, 2,545 tests plus the two known install-wizard failures) 2026-11-04 03:41 ET
- [ ] ~~A Security keyed by a SEDOL or LoanX alone~~ deferred to [190](190-a-securitys-key-is-any-identifier-class.md): the key class is read from about six places that know only CUSIP and ISIN (operator, 2026-11-03: "yes do option 1 and open the follow-up ticket"). Bloomberg ids and FIGIs as cross-references stay with it
- [x] Identifier Contracts for the SEDOL and the LoanX in the Security kind (`rules/merge/kinds/security.yaml`; normalizers from `rules/identifiers/`), without a verification: no matching rule reads them, so they need none until ticket 190 makes one; the Mapping Documents are regenerated 2026-11-04 03:41 ET
- [x] Funds with no series id: the registrant's Company is the fund (operator, 2026-11-03: "yes the company is the fund"), so there is nothing to build. Checked: 702 of the 703 registrants that file without a series id file nothing that names a series; each of their 729 filings carries a registrant LEI, which stays the Company's lookup (the operator ruled the SEC registrant LEI a lookup on the Company only); each is mastered as a Company by its CIK and its holdings link to that Company (`registrant_mdm_id`, ticket 79 part 2). The one registrant that files both kinds keeps its series as Funds and its series-less filings on the Company 2026-11-04 04:04 ET
  - [x] (2026-11-03 20:46 ET) Measured on the 2026 Q2 data set: 729 of 14,416 filings name no series id, from 703 registrants; every one of the 729 carries a registrant LEI; 679 registrants file once, 24 file two or three times and 23 of those use one name for all (one fund), one uses several names; 702 of the 703 registrants file nothing that names a series. So the registrant is the fund for 702 registrants; one registrant files both kinds and needs its own look
  - [ ] ~~Key the Fund by the registrant's CIK for a filing with no series id, its LEI an identifier; a test run~~ not built: the Company is the fund (the part above); a second master keyed by the same CIK would duplicate it
- [x] (2026-11-03 20:46 ET) The shared LEIs checked against the GLEIF Golden Copy (2026-09-11 16:00; the local capture, no download: its links pointed at the folder before ticket 73 renamed it, and are repointed). The 2026 Q2 data set has 15 LEIs on two or more series (not 16). GLEIF names one series for 12 of them (its legal name is that series' name); for 3 it names the adviser, the trust or the company (one of them on 27 series), not any series
  - [ ] ~~The matching rule keeps the LEI on the series GLEIF names, and keeps it as a filed value only on the others; the 3 LEIs GLEIF gives to the adviser, trust or company attach to no series; counts to the operator~~ deferred to [191](191-the-lei-on-the-series-gleif-names.md): it needs a GLEIF input to the Fund source (a new GLEIF step, a run input and a name comparison), a build of its own
- [x] (2026-11-03 20:46 ET) The one series with two LEIs: GLEIF gives one LEI the series' own fund name and the other a different fund's name, so the series keeps the first
  - [ ] ~~The matching rule keeps the LEI GLEIF names for the series and the other as a filed value~~ deferred to [191](191-the-lei-on-the-series-gleif-names.md): the same input
- [x] Learning → skill: `skills/security-master/SKILL.md`, "Every Security uniquely identifiable" (a SEDOL and a LoanX join, CINS is not read, the Company is the fund for a series-less filing) 2026-11-04 04:22 ET
