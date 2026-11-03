# 183: The 13F holdings reach silver once the manager filings are read

Priority: 183. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 13:55 ET, from [158](158-glossary-holds-only-real-terms.md) (the catalog's last silver definition).

Type: task. Status: resolved. Blocked by: none (the manager filings are ticket 184).

## Question

The 13F information tables name no manager (`rules/sources/sec.thirteenf.securities/source.yaml`: "the holdings wait for the manager filings"), so the source masters only the Securities, and no silver table for the holdings exists. A holding is a manager's position in a Security: which source reads the manager filings, and what does the silver holdings table hold (a link to the manager's Company, a link to the Security by CUSIP, and the row's own facts: shares, share type, value, put or call, discretion, voting authority)?

## Parts

- [ ] ~~Choose the source that reads the manager filings (the 13F cover page and its link to the information table) and its place on the load checklist~~ deferred to ticket 184: the holdings table is built keyed by the accession number, which the manager filing joins; no source reads the manager filings yet
- [x] The silver holdings table spec (2026-11-03 14:46 ET): `rules/sources/sec.thirteenf.securities/silver-holding.yaml` (`thirteenf_holding`, 11 columns): key accession number and holding index; the Security linked by CUSIP; the holding's own facts (shares, unit, value, put or call, discretion, voting authority), each with its definition (`discretion_type`: who decides the purchase and sale, as the manager states it). The issuer name, class title and FIGI are the Security's and are not in the table (the read's `sec_thirteenf_holding` lost them too); the manager, period and filing date wait for ticket 184. `tests/unit/test_silver_keeps_no_master_field.py` passes for the source
- [x] The `silver.land` step on the 13F target (2026-11-03 14:46 ET): `land_holding` waits for the merge, the read takes the accession number from the capture's folder (`context: accession_number: {segment: accession}`), the journal step waits for the landing; `tests/integration/test_thirteenf_holding_silver.py` on real workers on PG16: the order (no landing claimable before the merge), 3 holdings land with their facts and no Security field, and the older target and plan tests follow the new steps
- [x] Catalog (2026-11-03 14:46 ET): `catalog.plan()` lists `thirteenf_holding` with the definition on `discretion_type` (the mapping workbook is regenerated); closes ticket 158's last part
- [x] Learning → skill (2026-11-03 14:46 ET): none: the rules are already in `skills/data-modeling/SKILL.md` (no master field in silver; a table is a new table) and `data-onboarding` (a silver landing step); the filing is the join key between an information table and its manager filing
