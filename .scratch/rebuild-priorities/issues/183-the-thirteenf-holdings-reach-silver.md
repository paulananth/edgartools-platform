# 183: The 13F holdings reach silver once the manager filings are read

Priority: 183. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 13:55 ET, from [158](158-glossary-holds-only-real-terms.md) (the catalog's last silver definition).

Type: task. Status: open. Blocked by: the 13F manager filings (cover pages) are not read by any source yet.

## Question

The 13F information tables name no manager (`rules/sources/sec.thirteenf.securities/source.yaml`: "the holdings wait for the manager filings"), so the source masters only the Securities, and no silver table for the holdings exists. A holding is a manager's position in a Security: which source reads the manager filings, and what does the silver holdings table hold (a link to the manager's Company, a link to the Security by CUSIP, and the row's own facts: shares, share type, value, put or call, discretion, voting authority)?

## Parts

- [ ] Choose the source that reads the manager filings (the 13F cover page and its link to the information table) and its place on the load checklist
- [ ] The silver holdings table spec: grain, links (manager, Security), the holding's own facts, each with its definition (`discretion_type` is "who decides the purchase and sale: sole, shared or none", from the information table's `investmentDiscretion`); no master field copied (`tests/unit/test_silver_keeps_no_master_field.py`)
- [ ] The `silver.land` step on the 13F target, tests on real workers
- [ ] Catalog: the definition shows on the silver column (closes ticket 158's last part)
- [ ] Learning → skill
