# Gold links: by identifier, several kinds, Set Aside out of scope

Status: open
Type: task
Owner: claude (map decisions 7, 9, 10, 12, 13)
Blocked by: 02, 04

A link resolves by its identifier on any master of its kinds; a link may name several kinds; its test counts only rows whose
key the Set Aside table does not hold, and every one resolves to exactly one master. The reporting owner's two links become one,
`[person, company]` by CIK.

## Rulings (operator, 2026-11-28)

- How a spec whose links change is registered: "Compare table shape (Recommended)". Registration refuses only a change to
  what builds the table (columns, key, partition, checks, load mode); a change to links or wording rewrites the recorded spec
  with no new table. Evidence: every hosted silver table holds today's committed spec (21 of 21 digests equal), registration
  refuses any changed spec, and nothing reads a spec's links while landing (links add no column).
- Where a Security's venue comes from: "US listing MICs (Recommended)". A shared ticker resolves among the Securities with a
  listing on the cover's operating MIC, then the `US` ISIN. Found after the ruling: each hosted Security master already keeps
  its listings with their MIC (617,363 of 1,392,162 listings carry one, through the `iso-10383-mic` crosswalk of OpenFIGI's
  exchange codes), so Gold reads them from the mirrored master; no new field, code set or OpenFIGI reload is needed.

## Measured on hosted MDM and silver (read-only, 2026-11-28)

- Every silver CIK column and every MDM `cik` identifier is ten digits (no padding needed for the join).
- Distinct keys per CIK link: all keys / found through `master_binding` today / found by CIK on the link's kinds:
  13F filing 10 / 8 / 8; IPO 4,752 / 3,940 / 3,944; Form 4 position issuer 1,761 / 1,675 / 1,728; Form 4 owner-row issuer
  1,877 / 1,724 / 1,838; reporting owner 4,831 / 16 / 4,488; registration 650 / 533 / 533; registration lines 559 / 457 / 457;
  prospectus 1 / 1 / 1 (three tables); company facts 329 / 298 / 303; N-PORT registrant 1,947 / 1,947 / 1,947. No CIK of
  these links is held by two masters of the link's kinds. The keys still unresolved wait for ticket 07's load under the
  phase-2 company rule (Set Aside or mastered).
- Fund structures hold no CIK today, so `[company, fund_structure]` finds companies only until a fund-structure rule for SEC
  filers masters one.
- Registration and prospectus offering rows by how many Securities hold the ticker: none 403 rows (372 tickers, ticket 05's
  OpenFIGI input, loaded in ticket 07), one 240, two 3 (3 tickers). All 3 shared tickers have exactly one holder with a
  listing on the cover's operating MIC. Across MDM, 365 tickers are held by several Securities; 209 of them by none with a
  `US` ISIN.
- No silver ticker is lower case; cover wordings are mixed case, so the wording is matched upper-cased and trimmed.

## Hosted prediction (read-only, 2026-11-28; the new views' SQL rendered for PostgreSQL, `sec-cover-exchange` inline, Set Aside empty)

Rows resolved of rows with a key, today, before ticket 07's load: 13F filing manager 146 / 168; IPO filer 54,926 / 63,325;
Form 4 position issuer 14,054 / 14,331; reporting owner 5,240 / 5,743; owner-row issuer 5,551 / 5,743; registration
registrant 613 / 732; registration lines 23,774 / 27,415; registration ticker 243 / 645 (240 by one holder, all 3 shared by
venue; the other 402 wait for ticket 05's OpenFIGI input); prospectus 1 / 1, 6 / 6, 22 / 22, ticker 0 / 1 (a ticker no
Security holds yet); company facts 4,802,424 / 5,134,979; N-PORT registrant 5,347,869 / 5,347,869. Links found by a
source code are unchanged. Ticket 07 measures them again after its load, with the Set Aside table built.

## Checklist

- [x] GoF consult on `edgar_warehouse/gold/views.py` and silver registration: keep branches behind one `link_type`; a FROM-clause dialect entry for JSON arrays; `specs.shape` shared by both registers; the MySQL stage named from the shape (2026-11-28 09:42 ET)
- [x] Silver registration compares the table's shape; a links or wording change rewrites the recorded spec (PostgreSQL, MySQL): `test_a_spec_changed_only_in_links_or_wording_keeps_its_table_and_a_changed_shape_is_refused`, 29 passed on each engine (2026-11-28 09:42 ET)
- [x] Silver specs: every link names `kinds`; CIK links resolve by `identifier: cik`; the reporting owner's two links become one `[person, company]`; an issuer is `[company, fund_structure]`: 17 specs, spec checker tests 65 passed (2026-11-28 09:42 ET)
- [x] The silver context view shows `kinds`, `identifier` and `venue`: a numbered change file `001-link-kinds.sql`, PostgreSQL integration 23 passed (2026-11-28 09:42 ET)
- [x] Views and tests generated; a test per kind of link fails on today's generator: each new test errors there at `link["kind"]` (the specs name `kinds`); Gold tests 41 passed (2026-11-28 09:42 ET)
- [x] An identifier link counts canonical masters, so an alias and its survivor are one master: `test_an_identifier_an_alias_and_its_survivor_hold_is_one_master` (2026-11-28 09:42 ET)
- [x] A link's test leaves out a row whose identifier the Set Aside table holds; a link found by a source code has no identifier to leave out: `test_a_key_the_set_aside_table_holds_is_out_of_its_links_test` (2026-11-28 09:42 ET)
- [x] A Security's listing operating MIC readable by Gold from the mirrored master (from ticket 04): view `security_listing` from each master's listing details, its MIC to an operating MIC through `ref_iso_10383_mic`; `test_a_securitys_listings_are_one_gold_row_each_with_their_mic` (2026-11-28 09:42 ET)
- [x] A registration or prospectus ticker several Securities hold resolves by its cover's Trading Venue (`ref_sec_cover_exchange` to `ref_iso_10383_mic`'s operating MIC), then the `US` ISIN; a row whose wording `sec-cover-exchange` lacks, or which gives none, is out of the link test as "exchange not mapped" (from ticket 04): two tests, and 3 of 3 shared tickers on hosted (2026-11-28 09:42 ET)
- [x] Hosted prediction per link with the new views' SQL, counts here (2026-11-28 09:42 ET)
- [x] Dependency inference follows an identifier link to every source minting a master of its kinds by that identifier (2026-11-28 09:42 ET)
- [ ] `/code-review`
- [ ] Learning → skill
