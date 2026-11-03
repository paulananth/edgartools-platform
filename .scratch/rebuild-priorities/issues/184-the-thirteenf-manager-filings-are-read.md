# 184: The 13F manager filings are read, so a holding names its manager and period

Priority: 184. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 14:46 ET, from [183](183-the-thirteenf-holdings-reach-silver.md).

Type: task. Status: open. Blocked by: none.

## Question

`silver.thirteenf_holding` holds each holding by its filing's accession number and its place in the information table. The information table names no manager, no report period and no filing date; the manager filing (the 13F cover page, `primary_doc.xml`, or the filer's submissions list) holds them. Which source reads it, from which capture, and what does the silver filing table hold (accession number, manager CIK linked to its Company, report period, filing date, form, the manager's name only as MDM holds it)?

## Parts

- [ ] Count what is captured: 13F filings in the submissions captures (form 13F-HR and 13F-HR/A), and whether the cover pages are in a capture; counts only
- [ ] Choose the source and its place on the load checklist (the submissions lists already carry `accessionNumber`, `form`, `reportDate` and `filingDate` for every filer; the manager is the filer whose list holds the accession)
- [ ] The silver filing table spec (key: accession number; link: manager Company by CIK; time: report period as_of, filing date as_at) and a `silver.land` step; no master field copied (`tests/unit/test_silver_keeps_no_master_field.py`)
- [ ] `thirteenf_holding` finds its filing by accession number (a view or a documented join); the holdings stay append only
- [ ] Learning → skill
