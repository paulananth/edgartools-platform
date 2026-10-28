# 143: Silver keeps no master field

Priority: 143. Map: [Rebuild priorities](../map.md). Opened 2026-10-28 07:02 ET.

Type: task. Status: open, not started.
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
| `nport_holding` (N-PORT) | 9: CUSIP, ISIN, issuer LEI, currency code, asset category, issuer type, investment country, restricted, derivative category | CUSIP, ISIN (Security identifiers), issuer LEI (the issuer Company's identifier) | the six Security fields and the currency: ticket 138's "Most-filed value" part |
| `ownership_owner` (Forms 3/4/5) | 15: the owner's name, 8 address columns, 4 capacity flags (director, officer, ten-percent owner, other), officer title, other text | name (Person legal name), the 4 capacities (relationships with dates) | the address (8 columns), officer title, other text |
| `ownership_line` (Forms 3/4/5) | 2: security title, underlying security title | none | the class title on the Security: ticket 24 attaches a Form 4 line to its Security by class |

Not copies, so they stay: each table's link keys (`id`, `security_key`,
`series_id`, `registrant_cik`, `owner_record_key`, `rpt_owner_cik`,
`issuer_cik`) and the transaction's own facts (amounts, dates, codes, the
holder's valuation level and payoff profile).

## Parts

- [x] Skills say it (2026-10-28 07:02 ET): data-modeling, data-onboarding,
  refining-rules, security-master (PR #1199)
- [ ] `nport_holding`: the six fields and the currency reach the Security
  (ticket 138's part), then the 9 copies leave the spec
- [ ] `openfigi_listing`: check each column is on the Security in MDM, move
  any that is not, then retire the table
- [ ] `ownership_owner`: the address, officer title and other text reach MDM
  (decide with the operator: the address on the Person, the title and text on
  the capacity relationship), then the 15 copies leave; the table keeps the
  filing's owners as links
- [ ] `ownership_line`: the titles leave once ticket 24 attaches each line to
  its Security
- [ ] A test that refuses a silver spec column that a Dataset Contract of a
  linked kind also maps (link keys excepted), so a copy cannot come back
- [ ] Silver's stored tables: the writer adds columns but never drops them;
  say how a retired column leaves the local stores (the shared server needs
  its users told first)
- [ ] Tests, three-axis review, PR, CI green, merge, per table
- [ ] Learning → skill
