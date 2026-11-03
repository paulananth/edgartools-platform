# 184: The 13F manager filings are read, so a holding names its manager and period

Priority: 184. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 14:46 ET, from [183](183-the-thirteenf-holdings-reach-silver.md).

Type: task. Status: resolved. Blocked by: none.

## Question

`silver.thirteenf_holding` holds each holding by its filing's accession number and its place in the information table. The information table names no manager, no report period and no filing date; the manager filing (the 13F cover page, `primary_doc.xml`, or the filer's submissions list) holds them. Which source reads it, from which capture, and what does the silver filing table hold (accession number, manager CIK linked to its Company, report period, filing date, form, the manager's name only as MDM holds it)?

## Parts

- [x] Count what is captured (2026-11-03 16:38 ET): the captured submissions hold 76,230 main documents; 9,518 managers list at least one 13F report in their recent list, 318,205 13F-HR rows in all (298,585 holdings reports, 19,620 amendments), plus 72,148 notices (13F-NT) and a few hundred exemptions and confidential-treatment forms. No cover page is captured; only the recent list is (older pages are not in the capture), so older reports of the most active managers are missing until the additional pages are captured
- [x] The source (2026-11-03 16:38 ET): `sec.thirteenf.filings`, silver only (no MDM record), reading the managers' own submissions lists (the manager is the filer whose list holds the accession number); on the checklist after `sec.company` and `sec.thirteenf.securities` (`rules/source-sequence.yaml`, target `silver`)
- [x] The silver filing table (2026-11-03 16:38 ET): `rules/sources/sec.thirteenf.filings/silver-filing.yaml` (`thirteenf_filing`, 7 columns), keyed by accession number, the manager Company linked by CIK (`manager_mdm_id`), report period as_of and filing date as_at, one check (report not after filing); target `silver` = read, land, journal. `tests/integration/test_thirteenf_filing_silver.py` on real workers: 2 managers' lists land 6 reports and no 10-K, the journal notes each list, the manager's name is not copied; `tests/unit/test_silver_keeps_no_master_field.py` and the sequence tests pass
- [x] `thirteenf_holding` finds its filing by accession number (2026-11-03 16:38 ET): a documented join in both specs (`thirteenf_holding.accession_number = thirteenf_filing.accession_number`); both stay append only
- [x] Learning → skill (2026-11-03 16:38 ET): none new: the rules are in `skills/data-modeling/SKILL.md` (a silver row links to its master and copies none); that a document naming no filer is joined to it through the list that holds its id is this ticket's finding, recorded here
