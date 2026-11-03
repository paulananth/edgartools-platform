# 143: Silver keeps no master field

Priority: 143. Map: [Rebuild priorities](../map.md). Opened 2026-10-28 07:02 ET.

Type: task. Status: resolved.
Blocked by: none. Raised by the operator, 2026-10-28: "all master data fields
must be on mdm", then "silver must not have duplicate fields, it contredits the
data governance principle one system of record fix the skil and tabls".

## The rule

A master data field has one system of record: its master in MDM. A silver row
holds the transaction's own facts and its links to masters. It never copies a
master field, not even the value that row filed. The one source key a link
reads stays, because the silver writer lands it and fills the master id from it
once that record is mastered (`silver_writer/relational.py`). A field MDM lacks
moves to MDM first; then silver drops it.

## Found (2026-10-28 07:02 ET, the four silver table specs on `main`)

| Silver table | Master fields it copies | Already in MDM | Not yet in MDM |
|---|---|---|---|
| `openfigi_listing` (OpenFIGI) | all 11 columns: listing FIGI, ticker, exchange code, composite FIGI, share-class FIGI, name, security type, security type 2, market sector, security description, and the identifier asked | the listings (in the Security's record since ticket 120, found by the venue lookup since #1192), name, security types, market sector | security description, if MDM does not hold it yet (to check) |
| `nport_holding` (N-PORT) | 8: CUSIP, ISIN, issuer LEI, asset category, issuer type, investment country, restricted, derivative category (the currency code stays: the unit of the row's value; operator, 2026-10-28: "Keep it on the row (Recommended)") | CUSIP, ISIN (Security identifiers), issuer LEI (the issuer Company's identifier) | the six Security fields (currency included): ticket 138's "Most-filed value" part |
| `ownership_owner` (Forms 3/4/5) | 15: the owner's name, 8 address columns, 4 capacity flags (director, officer, ten-percent owner, other), officer title, other text | name (Person legal name), the 4 capacities (relationships with dates) | the address (8 columns), officer title, other text |
| `ownership_line` (Forms 3/4/5) | 2: security title, underlying security title | none | the class title on the Security: ticket 24 attaches a Form 4 line to its Security by class |

Not copies, so they stay: each table's link keys (`id`, `security_key`,
`series_id`, `registrant_cik`, `owner_record_key`, `rpt_owner_cik`,
`issuer_cik`) and the transaction's own facts (amounts, dates, codes, the
holder's valuation level and payoff profile).

## Parts

- [x] Skills say it (2026-10-28 07:02 ET): data-modeling, data-onboarding,
  refining-rules, security-master (PR #1199)
- [x] `nport_holding` (2026-10-28 08:12 ET): the six facts reach the Security and the 8
  copies leave the spec, #1200; live at ticket 138's switch-on
- [x] `openfigi_listing` (2026-11-03 13:56 ET): every column is on the Security in MDM: the Security's `details.listings` holds every listing whole, one detail row per FIGI (ticket 120, operator: "all fields from open figi must be in the security master"), and the name, security types and market sector are record fields; the share class and composite FIGIs and the ticker are its cross-references. So the table is a copy and is retired: `silver-listing.yaml`, the catalog's special cases for it (`catalog.py`), and the integration test that landed it (replaced by `test_every_listing_of_the_source_extract_is_a_detail_row_of_its_security_in_mdm`: 19 listings, each a detail row). The source's `listings` table stays: it feeds the detail rows
- [x] `insider_ownership` (was `ownership_owner`) (2026-11-03 13:56 ET): 13 of the 15 copies leave the reading and the spec: the name, the officer title and the director, officer and ten-percent capacities are the Person's and its dated relationships in MDM already (`owner_record` carries them); the owner's address (9 columns) is never captured into MDM by the Person consumer spec, so it is kept nowhere (the filing in bronze holds it), decided under the rule that MDM refuses it; `is_other` and `other_text` stay because MDM has no relationship type for that capacity: ticket 182
- [ ] ~~`insider_position` (was `ownership_line`): the titles leave once ticket 24 attaches each line to its Security~~ deferred to ticket 24: the class title belongs on the Security, which a Form 4 line does not reach yet
- [x] A test that refuses a silver spec column that a Dataset Contract of its source also maps (2026-11-03 13:56 ET): `tests/unit/test_silver_keeps_no_master_field.py` (13 sources; link keys, the record key, the key and the dates are excepted; `KEPT` names a column kept by a ruling: N-PORT's currency code). It fails on the old owner spec (5 copies) and the old listing spec (1: the name); it matches by source field name, so a copy renamed in silver is not caught
- [x] Silver's stored tables (2026-11-03 13:56 ET): a retired column leaves a store by a new table, not a drop (the writer adds columns and never drops them; a changed spec is refused for a registered table): `skills/data-modeling/SKILL.md`; the local store holds no Silver, so nothing is dropped now
- [x] Tests (2026-11-03 13:56 ET): tests/mdm, tests/unit, tests/architecture (2467), the ownership and OpenFIGI engine and integration tests (17 and 59) pass; the catalog tests use a company-facts check where they used the listing table
- [x] Learning → skill (2026-11-03 13:56 ET): `skills/data-modeling/SKILL.md` (the new-table rule and the guard test); the rule itself was in the skills since #1199
