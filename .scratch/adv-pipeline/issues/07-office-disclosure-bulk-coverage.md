# 07 — Does the advFilingData Archive Carry Office/Disclosure Equivalents?

Type: research
Status: resolved
Blocked by: none
Blocks: none

## Question

Surfaced by ticket 02's answer (Q4): `edgar_warehouse/application/adv_bulk_ingest.py`
only populates `sec_adv_filing` and `sec_adv_private_fund` from the monthly
`advFilingData` bulk feed. `sec_adv_office` and `sec_adv_disclosure_event` are populated
only by the separate EDGAR-native parser (`edgar_warehouse/parsers/adv.py`), which runs
for a small subset of advisers (those who also file ADV documents directly on EDGAR).
Since `edgar_warehouse/mdm/adv_bulk.py`'s `resolve_advisers_bulk` reads `sec_adv_office`
for `hq_city`/`hq_state`, the vast majority of advisers resolved via the bulk feed
currently get null HQ data.

A June 2026 `advFilingData` ZIP (`ADV_Filing_Data_20260601_20260630.zip`) contains ~101
files total — the parser currently only reads 4 of them (`IA_ADV_Base_A/B`,
`ERA_ADV_Base`, `IA/ERA_Schedule_D_7B1/7B2`, `ADV_Filing_Types`). ~95 other Schedule
A/B/D/R and DRP tables are unexamined.

Resolve, against the actual downloaded archive contents (re-fetch per the command in
`docs/release-readiness/adv-bulk-ingest-format-change-2026-07-24.md` if the prior
session's scratchpad copy is gone — SEC requires a `User-Agent` with an email or returns
403):

1. Does the archive contain an office/location schedule (e.g. `IA_Schedule_D_1B`,
   "Other Offices," or similar) with per-firm address/city/state data equivalent to what
   `sec_adv_office` expects? Inspect actual column headers and a sample of populated rows,
   not just the filename.
2. Does the archive contain a disclosure-event schedule (DRP — Disclosure Reporting Page
   — tables, e.g. criminal/regulatory/civil DRP schedules under Item 11) with data
   equivalent to what `sec_adv_disclosure_event` expects?
3. For each schedule found: is it keyed by `FilingID` the same way `IA_ADV_Base_A/B` and
   `IA_Schedule_D_7B1/7B2` are (so it joins cleanly against the same `filing_id` the
   existing parser already extracts), or does it need separate identity resolution?
4. If no equivalent exists in this archive at all, is there a different bulk product
   (checked in ticket 01's research: Firm Roster CSV, IAPD Compilation XML) that carries
   office/disclosure data at bulk scale, even partially?

## Answer

**Method:** downloaded and inspected the real June 2026 `advFilingData` archive
byte-for-byte (primary source, not a secondary write-up). Checked
`reports.adviserinfo.sec.gov/reports/foia/reports_metadata.json` first for a
newer month — as of this session the most recent `advFilingData` entry is
still June 2026 (`ADV_Filing_Data_20260601_20260630.zip`, uploaded
2026-07-01; no July 2026 entry yet, consistent with the "uploaded on the 1st
of the following month" pattern already observed for June). Fetched:

```
curl -A "EdgarTools Platform thepaulananth@gmail.com" \
  "https://reports.adviserinfo.sec.gov/reports/foia/advFilingData/2026/ADV_Filing_Data_20260601_20260630.zip"
```

9,057,014 bytes — matches the metadata manifest's `size` field exactly.
`unzip -l` confirms **101 files**, matching ticket 01's prior count. Full
namelist inspected (not just the 4 files the parser already reads).

### Q1 — Office data: YES, in a dedicated schedule file, separate from the 4 files already read

`IA_Schedule_D_1F_20260601_20260630.csv` (1.8 MB, **13,109 data rows**) and
its ERA counterpart `ERA_Schedule_D_1F_20260601_20260630.csv` (214 data
rows) are Form ADV Schedule D **Item 1.F ("Other Offices")** — the
multi-office list, distinct from the single principal-office address
embedded in the base file (see below). Header:

```
FilingID,Street 1,Street 2,City,State,Country,Postal Code,Private Residence,
Telephone Number,Facsimile Number,Branch Number,Employees,BD,Bank,Insurance,
Commodity,Municipal,Accounting,Law,Other
```

Real sample rows (IA, FilingID 2115188 — a firm with 5 offices in this one
delta):

```
2115188,"200 SEVEN FIELDS BOULEVARD",,"SEVEN FIELDS","PA","United States","16046","N","724-772-9811",,"130641","7","Y","N","Y","N","N","N","N",
2115188,"454 STATE ROUTE 28",,"BRIDGEWATER","NJ","United States","08807","N","908-429-8249",,"131015","5","Y","N","Y","N","N","N","N",
2115188,"ONE PNC","249 FIFTH AVE FL 29","PITTSBURGH","PA","United States","15222","N","412-762-6120",,"119968","35","Y","N","Y","N","N","N","N",
```

Real sample row (ERA, FilingID 2115264 — UK-based ERA, 2 UK offices):

```
2115264,"SPACES, 9 GREYFRIARS RD",,"READING",,"United Kingdom","RG1 1NU","N","441189517000","441912446000",,"1","N","N","N","N","N","N","N",
"ALL OFFICES PROVIDE INVESTMENT ADVISORY FUNCTIONS; AND IN ADDITION NEWCASTLE PROVIDES FINANCE/ACCOUNTING AND COMPLIANCE SUPPORT."
```

This is real, populated, per-office data: street address, city, state,
country, postal code, branch number, employee count, and business-line
flags — far richer than the existing `sec_adv_office` schema's
`office_name`/`city`/`state_or_country`/`country`/`is_headquarters`
columns need.

**Not embedded in `IA_ADV_Base_A/B`, contrary to one of the two
hypotheses in the question.** Grepped the actual `IA_ADV_Base_A` header for
address-like columns and found only two *single*-address blocks:

- `1F1-Street 1/2/City/State/Postal` — the one principal office/place of
  business (Item 1.F.1), not the "other offices" list.
- `1G-Street 1/2/City/State/Postal` — the books-and-records address
  (Item 1.G), also a single address, not a list.

`IA_ADV_Base_B` has no office/address columns at all (only Items 2 and 3).
So the base files only ever carry **one** address per firm; the full
multi-office list lives exclusively in the separate `Schedule_D_1F` files.

### Q2 — Disclosure/DRP data: YES, four dedicated schedule files, separate from the 4 files already read

Four real per-event DRP files exist, `IA_` and `ERA_` prefixed (8 files
total):

| File | IA data rows | ERA data rows |
|---|---|---|
| `*_DRP_Criminal_*.csv` | 537 | 0 (header only this month) |
| `*_DRP_Regulatory_*.csv` | 7,643 | 79 |
| `*_DRP_Civil_Judicial_*.csv` | 269 | 15 |
| `*_DRP_Advisory_Affiliates_*.csv` | 4,242 | 88 |

`IA_DRP_Regulatory_20260601_20260630.csv` header (Item 11.C/D/E/F/G):

```
FilingID,Initial/Amended,11.C(1),11.C(2),...,11.G.,Filed Against,ReferenceID,
...,Initiator Type,Initiated By,Principal Sanction,Other Sanctions,
Date Initiated,...,Case Number,Employing Firm,Principal Product,...,
Allegations,Status,...,Resolution,Resolution Date,...,Monetary Sanction,
Monetary Amount,Revocation/Expulsion/Denial,Censure,Bar,
Disgorgement/Restitution,Cease and Desist/Injunction,Suspension,
Other Sanctions Ordered,Sanction Detail,Summary
```

Real sample row (truncated):

```
FilingID=2055963, Initial/Amended=AMENDED, 11.E(3)=Y, Filed Against=Affiliates,
ReferenceID=1771958, Initiator Type=SRO, Initiated By=FINRA,
Principal Sanction=Censure, Date Initiated=02/19/2021,
Case Number=2020065242701, Principal Product="Equity Listed (Common & Preferred Stock)",
Allegations="WITHOUT ADMITTING OR DENYING THE FINDINGS, THE FIRM CONSENTED TO
  SANCTIONS OF THE ENTRY OF FINDINGS THAT IT CONDUCTED A SECURITIES BUSINESS
  WHILE FAILING TO MAINTAIN THE MINIMUM REQUIRED NET CAPITAL...",
Status=Final, Resolution="Acceptance, Waiver & Consent(AWC)",
Resolution Date=02/19/2021, Monetary Sanction=Y, Monetary Amount=5000,
Sanction Detail="THE FIRM HAS TAKEN NUMEROUS ACTIVE MEASURES..."
```

`IA_DRP_Criminal` and `IA_DRP_Civil_Judicial` are the same shape with their
own Item-11-subsection-appropriate columns (11.A/11.B for Criminal,
11.H for Civil Judicial) — real case-level dates, courts, dispositions, and
narrative summaries, not just Y/N flags.

`IA_DRP_Advisory_Affiliates_20260601_20260630.csv` is the linkage/index
table tying a `(FilingID, ReferenceID)` disclosure event to who it was
filed against:

```
FilingID,ReferenceID,Disclosure Type,CRD Number,Affiliate Type,Registered,Affiliate Name
2055963,1771958,"Regulatory Action",153157,"Firm","Y","KAPITALL GENERATION, LLC"
2057846,1772807,"Regulatory Action",5287262,"Individual","Y","RISER WHITLOCK, SUSAN, ROBIN"
```

This is exactly the shape `sec_adv_disclosure_event` needs
(`disclosure_category`, `event_date`, `description`) and considerably
richer (case numbers, sanctions, monetary amounts, affiliate linkage) than
the current schema's columns require.

**Not embedded (as full events) in `IA_ADV_Base_A`.** `IA_ADV_Base_A`
does carry Item 11 columns (`11`, `11A1`, `11A2`, `11B1`, `11B2`, `11C1`...
`11H2`), but these are **firm-level Y/N summary flags only** ("has this firm
ever had any disclosure of this subtype") — no dates, no case numbers, no
narrative, no per-event granularity. The actual DRP event records live
exclusively in the four separate `DRP_*` files. `IA_ADV_Base_B` has no
Item 11 columns at all.

### Q3 — FilingID join key: YES, on every candidate file, both IA and ERA variants

`FilingID` is the first column of every file inspected above:
`IA_Schedule_D_1F`, `ERA_Schedule_D_1F`, `IA_DRP_Criminal`,
`IA_DRP_Regulatory`, `IA_DRP_Civil_Judicial`, `IA_DRP_Advisory_Affiliates`,
and their ERA counterparts. This is the identical join key
`IA_ADV_Base_A/B` and `IA/ERA_Schedule_D_7B1/7B2` already use, so all of
these files join cleanly with no separate identity-resolution work.

One schema-shape note for whoever implements this (research only, not
deciding it here — flagging for ticket 08/implementation): the *existing*
`sec_adv_office`/`sec_adv_disclosure_event` silver tables are keyed on
`(accession_number, {office_index,event_index})`, not `filing_id` directly
— `accession_number` is populated by `edgar_warehouse/parsers/adv.py` from
a real EDGAR accession number. `adv_bulk_ingest.py` already solves the
mismatch for `sec_adv_filing`/`sec_adv_private_fund` by synthesizing
`accession_number = f"iapd-adv:{filing_id}"` (see
`adv_bulk_ingest.py:151`) so bulk-sourced rows share the same primary-key
shape as EDGAR-sourced rows. A bulk office/disclosure loader would need the
same synthesis (`iapd-adv:{filing_id}` as `accession_number`, with a
`(FilingID, Branch Number)` / `(FilingID, ReferenceID)` ordinal used to
derive `office_index`/`event_index`) to land in the existing tables without
a schema change — confirmed as a viable pattern, not implemented here per
this ticket's research-only scope.

### Q4 — Firm Roster CSV / Compilation XML fallback: not reached; not needed

Real per-office and per-disclosure-event data was found directly in the
`advFilingData` archive (Q1/Q2), so the fallback check specified in the
ticket ("if you find nothing relevant... also check the Firm Roster
CSV/Compilation XML") does not apply. For completeness, citing
`.scratch/adv-pipeline/research/01-iapd-format-scope-findings.md` (already
verified against the official XSD in that session, not re-fetched here):
the Compilation XML feed's `Item7BType` has exactly one Y/N attribute with
no children, and the Firm Roster CSV carries only aggregate private-fund
*counts*. Neither format was ever checked for office/disclosure columns in
ticket 01 specifically, but both are documented there as coarse,
aggregate-only products by nature (point-in-time roster snapshots), which
makes them structurally unlikely to carry the office-list or
per-DRP-event granularity found directly in `advFilingData`. Not
independently re-verified for office/disclosure columns in this session
since Q1/Q2 already resolved the question from a materially better source.

## Summary

| Question | Answer |
|---|---|
| Office data present in bulk archive? | Yes — `IA_Schedule_D_1F` / `ERA_Schedule_D_1F`, 13,109 / 214 real rows |
| Office data embedded in Base_A/B instead? | No — Base_A has only 1 principal-office address (1F1) + 1 books-and-records address (1G), not the multi-office list |
| Disclosure/DRP data present in bulk archive? | Yes — 4 files × IA/ERA (`DRP_Criminal`, `DRP_Regulatory`, `DRP_Civil_Judicial`, `DRP_Advisory_Affiliates`), 537–7,643 real IA rows per file this month |
| Disclosure data embedded in Base_A instead? | No — Base_A has only Y/N summary flags (`11`, `11A1`...`11H2`), no dates/case numbers/narrative |
| FilingID join key present? | Yes, on all 6 file families (IA + ERA), first column, identical to existing parser's join key |

**Bottom line: the fix for the bulk office/disclosure coverage gap
described in the ticket context is a parser-extension problem, not a
missing-data problem.** All the data the ticket asked about exists in the
archive the pipeline already downloads every month, joins cleanly on the
existing `FilingID` key, and is real per-office/per-event data (not just
flags) — `adv_bulk_ingest.py` simply doesn't read these 6 additional file
families yet. Implementation (parsing these files, synthesizing
`accession_number`, wiring into `sec_adv_office`/`sec_adv_disclosure_event`)
is out of scope for this research ticket.
