# Research: Scope of the IAPD Bulk Format Change

Ticket: `.scratch/adv-pipeline/issues/01-confirm-scope-of-iapd-format-change.md`
Date: 2026-07-24
Method: primary sources only — SEC.gov, adviserinfo.sec.gov (IAPD), iard.com (FINRA,
operator of IAPD), and actual files downloaded and inspected byte-for-byte. All SEC.gov
fetches used `curl -A "EdgarTools Platform thepaulananth@gmail.com"` (a generic
User-Agent gets 403). All files referenced below were re-downloaded this session to
`/private/tmp/claude-501/.../scratchpad/iapd/` (ephemeral — re-fetch commands included).

**Revision note:** this document's first draft concluded the old relational per-fund
format was discontinued after 2024-12-31. That conclusion was **wrong** — it was based on
inspecting only one of two distinct manifests the IAPD app calls (see "Two different
services, two different manifests" below). The corrected finding, below, is that the
relational per-fund format is **still being produced monthly, currently, and is bulk-
downloadable** — just from a different URL than the one the sec.gov FOIA page's static
HTML links to. This correction was caught by re-checking the `/adv` route's actual data
source before finalizing, rather than assuming it matched `/compilation` because both
called a same-named `getCompilationReport()` method on different injected services.

## Summary answer

1. **No — the Firm Roster CSV is not the only bulk product, and the old relational
   per-fund format is not discontinued.** It has moved from one continuing document
   (`sec.gov`'s FOIA page, terminated 2024-12-31) to an actively-maintained **monthly
   delta feed** served from `adviserinfo.sec.gov`'s `/adv` route, backed by
   `reports.adviserinfo.sec.gov/reports/foia/reports_metadata.json` under the
   `advFilingData` key. Each month's ZIP contains the full ~100-file relational schema
   (`IA_ADV_Base_A/B`, `IA_Schedule_D_7B1`, `IA_Schedule_D_7B2`, `ADV_Filing_Types`, and
   ~95 other schedule tables, `IA_`/`ERA_` variants of each) with real per-fund rows
   (fund name, Fund ID/PFID, AUM, fund type). Monthly files exist for **all of 2025
   (12 months) and 2026 through June** (6 months, most recent uploaded 2026-07-01) —
   picking up with zero gap exactly where the pre-2025 historical archive (below) ends.
2. **Yes — bulk per-fund detail is obtainable, via the monthly `advFilingData` feed.**
   This supersedes the original Q2 answer ("per-adviser lookup only") for anything filed
   from 2025-01-01 onward.
3. **Yes** (unchanged from the first draft) — the separate Firm Roster CSV's aggregate
   columns are real, populated data and carry usable signal even independent of the
   richer relational feed.
4. **No CSV-specific dictionary for the Firm Roster CSV** (unchanged) — but the relational
   `advFilingData` feed's column headers are the *same* Form-ADV-item-numbered convention
   the old parser (`adv_bulk_ingest.py`) already targets, decodable against the Form ADV
   Part 1A instructions PDF, same as before.

---

## Two different services, two different manifests — the mistake and the fix

`adviserinfo.sec.gov` is an Angular SPA (`curl` gets an empty 9 KB shell — real content is
client-side). Reading the compiled app bundle
(`https://adviserinfo.sec.gov/main.7005adea37a6f33f.js`, fetched directly, 1.3 MB) shows
its route table:

```
{path:"compilation", ..., page: INVESTMENT_ADVISOR_DATA, resolve:{query: Xd2-resolver}}
{path:"adv",          ..., page: FIRM_FORM_ADV,          resolve:{query: foiaReportService-resolver}}
```

Both resolvers call a method literally named `getCompilationReport()` — but on **two
different injected services**, and their method bodies build **two different URLs**:

```js
// compilationReportService.getCompilationReport()  (backs /compilation)
const t = `${this.config.getExternalSite("reports")}/reports/CompilationReports/CompilationReports.manifest.json`;

// foiaReportService.getCompilationReport()  (backs /adv)
const t = `${this.config.getExternalSite("reports")}/reports/foia/reports_metadata.json`;
```

The first draft of this research fetched only the first URL, saw a 3-feed XML manifest
with no fund data, and — because both routes call a same-named method — wrote "both
routes resolve to the identical call" without verifying the second URL. That was an
inference, not a fetch, and it was wrong. The two manifests are genuinely different
products.

### Manifest 1 — `CompilationReports.manifest.json` (backs `/compilation`)

```json
{"files": [
  {"name": "IA_FIRM_SEC_Feed_07_23_2026.xml.gz", "size": "78 MB", "date": "07/23/2026"},
  {"name": "IA_FIRM_STATE_Feed_07_23_2026.xml.gz", "size": "69 MB", "date": "07/23/2026"},
  {"name": "IA_INDVL_Feed_07_23_2026.xml.zip", "size": "167 MB", "date": "07/23/2026"}
]}
```

Downloaded and inspected `IA_FIRM_SEC_Feed_07_23_2026.xml.gz` (7.2 MB gz → 81.6 MB XML,
23,602 `<Firm>` records). Confirmed against the official XSD
(`IAPDSECBulkFeed.xsd`, from FINRA/IARD's `firm_compilation.zip`, still hosted live at
`iard.com/firm-compilation`): `Item7BType` has exactly one attribute, `Q7B` (Y/N/null),
no children — a point-in-time roster snapshot with no fund detail at all, not even
aggregate counts. This part of the original research still stands as an accurate
description of *this one feed* — it's just not SEC's only or primary bulk product, as
originally concluded.

### Manifest 2 — `reports/foia/reports_metadata.json` (backs `/adv`) — the one that was missed

Fetched directly this session:

```
https://reports.adviserinfo.sec.gov/reports/foia/reports_metadata.json
```

Top-level keys: `advW`, `advFirmCRSDocs`, `advFilingData`, `advBrochures`, `advFirmCRS`.
`advFilingData` ("Form ADV Part 1 Data Files") lists monthly files:

```
2025: 12 files (January .. December)
2026: 6 files  (January .. June — most recent, uploaded 2026-07-01)
2024: (key present, empty — no files)
```

e.g. (verbatim from the fetched JSON):

```
{"displayName":"June","fileName":"ADV_Filing_Data_20260601_20260630.zip",
 "size":9057014,"year":"2026","fileType":"advFilingData",
 "uploadedOn":"2026-07-01 21:13:14"}
```

The download URL pattern, read from the bundle's list-building code
(`main.7005adea37a6f33f.js`):

```
${this.reportsUrl}/reports/foia/${categoryKey}/${year}/${fileName}
```

i.e. `https://reports.adviserinfo.sec.gov/reports/foia/advFilingData/2026/ADV_Filing_Data_20260601_20260630.zip`
— fetched directly this session (HTTP 200, `content-length: 9057014`, `last-modified:
2026-07-01`, confirmed live via HEAD + full GET).

### What's inside a current monthly `advFilingData` ZIP — downloaded and inspected

`ADV_Filing_Data_20260601_20260630.zip` (June 2026, 9.06 MB compressed → 74.2 MB
uncompressed, 101 files) contains the **full old relational schema**, `IA_` and `ERA_`
variants of each:

```
ADV_Filing_Types_20260601_20260630.csv
IA_ADV_Base_A_20260601_20260630.csv        ERA_ADV_Base_20260601_20260630.csv
IA_ADV_Base_B_20260601_20260630.csv
IA_Schedule_D_7B1_20260601_20260630.csv    ERA_Schedule_D_7B1_20260601_20260630.csv
IA_Schedule_D_7B2_20260601_20260630.csv    ERA_Schedule_D_7B2_20260601_20260630.csv
... (~95 more Schedule A/B/D/R, DRP, and CIK tables, IA_ and ERA_ prefixed)
```

Extracted `IA_Schedule_D_7B1_20260601_20260630.csv` (13,799 data rows) and confirmed real,
populated per-fund rows:

```
"FilingID","Fund Name","Fund ID","ReferenceID","State","Country","3(c)(1) Exclusion",
"3(c)(7) Exclusion","Master Fund","Feeder Fund",...,"Fund Type","Fund Type Other",
"Gross Asset Value","Minimum Investment","Owners",...

2107670,"PALM PEAK CAPITAL FUND I, L.P.",805-4964869201,518607,"Delaware","United States",
"N","Y","N","N","","","N","","N","Private Equity Fund","",321687148,0,57,4,54,...
```

Real fund name, real Fund ID (`805-4964869201` — the same PFID convention as the
Form ADV Schedule D 7.B.(1) per-adviser PDF), fund type, and gross asset value — exactly
the shape `AdvBulkFund`/`sec_adv_private_fund` need.

### The existing parser code already targets this exact file shape

`edgar_warehouse/application/adv_bulk_ingest.py`'s filename regexes were tested directly
against this June 2026 ZIP's real `namelist()` (Python `re.search`, same call the parser
makes):

```python
r"(?:IA|ERA)_ADV_Base(?:_A)?_[^/]*\.csv$"      -> matches ERA_ADV_Base_..., IA_ADV_Base_A_..., IA_ADV_Base_B_...
r"(?:IA|ERA)_Schedule_D_7B1_[^/]*\.csv$"       -> matches ERA_Schedule_D_7B1_..., IA_Schedule_D_7B1_...
r"(?:IA|ERA)_Schedule_D_7B2_[^/]*\.csv$"       -> matches ERA_Schedule_D_7B2_..., IA_Schedule_D_7B2_...
r"ADV_Filing_Types_[^/]*\.csv$"                -> matches ADV_Filing_Types_...
```

**Every regex the current parser code uses matches real files in this product, with real
per-fund data inside.** The originally-reported "blocker" (parser returns zero rows) was
caused by staging the *wrong* SEC product (the Firm Roster CSV from the sec.gov
data-research bulk page) — not by SEC discontinuing the format the parser targets. That
format is alive, monthly, and reachable; it was just never fetched last session because
the operator/session downloaded from the wrong page.

### Why the sec.gov FOIA page looked like a dead end

`https://www.sec.gov/foia-services/frequently-requested-documents/form-adv-data` (the
page checked, both last session and again this session) has a static "Form ADV Part 1
Data Files" section listing exactly three links:

```
From ADV Part 1 - October 19, 2000, to November 4, 2011           (adv-filing-data-20001019-20111104.zip)
From ADV Part 1 - November 5, 2011, to December 31, 2024 - Part 1 (adv-filing-data-20111105-20241231-part1.zip)
From ADV Part 1 - November 5, 2011, to December 31, 2024 - Part 2 (adv-filing-data-20111105-20241231-part2.zip)
```

Confirmed via range-request inspection of the ZIP's internal file names (no full download
needed — read local file headers / central directory directly): these two 2011-2024 zips
contain the exact same relational file family
(`ADV_Filing_Types_20111105_20241231.csv`, `IA_Schedule_D_7B1_20111105_20241231.csv`,
`IA_Schedule_D_7B2_20111105_20241231.csv`, `IA_Schedule_D_10A_...`, 41 Schedule_D/R tables
total) — this is the pre-2025 chapter of the *same* product family as the June 2026
monthly file, just packaged as one multi-year zip instead of monthly deltas.

The page's own text says exactly this, and is accurate — it was just easy to
under-read on a first pass:

> "Form ADV Data from January 1, 2025, to present is available on the Investment Adviser
> Public Disclosure website (https://adviserinfo.sec.gov/adv). For historical data prior
> to January 1, 2025, Form ADV Part 1 ... Data Files ... is available in .csv format,
> below."

The static HTML page simply doesn't hyperlink the current (2025+) files directly — it
points to `adviserinfo.sec.gov/adv`, a JS SPA whose actual data source (a JSON manifest
one API call away) is the monthly `advFilingData` feed documented above. `curl`-ing
`/adv` without following into the app bundle looks identical to `curl`-ing
`/compilation` (both return an empty SPA shell) — the two routes only look the same until
you read which service each one's Angular resolver actually calls.

**Timeline, reconciled and gap-free:**

| Period | Format | Location |
|---|---|---|
| 2000-10-19 to 2011-11-04 | relational, per-fund | `sec.gov` FOIA page, static zip |
| 2011-11-05 to 2024-12-31 | relational, per-fund | `sec.gov` FOIA page, static zip (2 parts) |
| 2025-01-01 to present (monthly) | relational, per-fund | `adviserinfo.sec.gov/adv` → `reports.adviserinfo.sec.gov/reports/foia/advFilingData/<year>/<file>.zip` |

No discontinuity in the relational/per-fund format at any point — only a change in
*where* and *how often* it's published starting exactly 2025-01-01.

---

## Q1 — Is the Firm Roster CSV SEC's only bulk product, or does a separate relational/Schedule-D-detail product exist elsewhere?

**No, it is not the only product.** SEC/IAPD currently maintains (at least) three
distinct bulk products concurrently:

1. **Firm Roster CSV** (`sec.gov` data-research bulk-data page) — monthly, point-in-time,
   aggregate-only for private funds. This is the product last session downloaded and
   found "changed."
2. **IAPD Compilation XML feeds** (`adviserinfo.sec.gov/compilation`,
   `CompilationReports.manifest.json`) — refreshed same-day, point-in-time, only a Y/N
   flag for private funds (less detail than #1, confirmed against official XSD).
3. **`advFilingData` monthly relational feed** (`adviserinfo.sec.gov/adv`,
   `reports/foia/reports_metadata.json`) — monthly filing-activity deltas, full
   `IA_Schedule_D_7B1`/`7B2` per-fund records, continuing the pre-2025 FOIA archive with
   no gap. **This is the product `adv_bulk_ingest.py` was written against, and it still
   exists, current, and downloadable.**

No fourth format was found; `adviserinfo.sec.gov`'s own route table
(`compilation`, `adv`, `individual/summary`, `resources`) is exhaustive of what the SPA
itself considers its bulk-data surface, and both `compilation` and `adv` were run to
ground (their actual backing manifests fetched and inspected, not inferred).

---

## Q2 — Is per-fund Schedule 7.B.(1)/(2) detail obtainable any other way at scale?

**Yes — via the `advFilingData` monthly feed described above, for anything filed
2025-01-01 to present, plus the two static historical zips for everything filed
2000-10-19 through 2024-12-31.** This supersedes the original conclusion that per-adviser
lookup was the only route. Per-adviser PDF lookup (confirmed separately — see below) also
works and is a legitimate fallback/cross-check for a single firm, but is not the primary
route now that the bulk monthly feed is confirmed.

For completeness, per-adviser lookup was also confirmed populated: fetched
`https://reports.adviserinfo.sec.gov/reports/ADV/1588/PDF/1588.pdf` (Davenport & Company
LLC, CRD 1588 — chosen because the Firm Roster CSV shows 3 hedge funds, $709.9M in
private-fund assets for this firm). Converted with `pdftotext` (required `brew install
poppler`, not present in the environment) and confirmed a fully populated Section 7.B.(1):
fund name "EWF PARTNERS II LLC", PFID `805-4154444394`, jurisdiction, fund type, AUM.

**Ingestion-strategy implication (flagging for ticket 02, not deciding it here) — now
verified, not inferred:** the `advFilingData` feed is confirmed to be a **monthly delta of
filing activity**, not a full-universe snapshot. Extracted and row-counted
`IA_ADV_Base_A_20260601_20260630.csv` directly: **2,938 firm-filing rows** for June 2026,
against the ~17,073-row registered-adviser universe counted from the July 2026 Firm
Roster CSV (Q3) — i.e. only ~17% of registered firms filed or amended during that single
month, ruling out "one month = full universe." Since RIAs must reaffirm/amend Form ADV at
least annually, a rolling ~13-month window of monthly deltas (union, deduped by
CRD/FilingID, keeping the latest per firm) should capture the full active-adviser universe
at least once — but ticket 02 should still explicitly verify no firm goes stale for >13
months before committing to that window size.

---

## Q3 — Do the Firm Roster CSV's aggregate private-fund columns carry usable signal even without per-fund identity?

Unchanged from the first pass — **yes**, verified against real, populated data (not
column-name inference). Parsed `IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622660.CSV`
(registered advisers, from the July 2026 sec.gov bulk-data ZIP, 17,073 rows, 448 data
columns) with Python's `csv` module. Scanning the first 16,935 data rows:

| Column | Populated (non-blank/non-"No") |
|---|---|
| `7B` (Y/N — do you advise any private fund) | 5,970 / 16,935 = "Y" |
| `Count of Private Funds - 7B(1)` | 16,935 / 16,935 (always populated, incl. "0") |
| `Any Hedge Funds` | 2,577 / 16,935 = "Y" |
| `Total number of Hedge funds` | 2,577 / 16,935 (populated whenever "Any Hedge Funds"="Y") |
| `Any PE Funds` | 2,508 / 16,935 = "Y" |
| `Total number of PE funds` | 2,508 / 16,935 |
| `Total Gross Assets of Private Funds` | 16,935 / 16,935 (always populated) |
| `Count of Private Funds - 7B(2)` | 16,935 / 16,935 (always populated) |

Sample real row (Davenport & Company LLC, CRD 1588): `7B=Y`, `Count of Private Funds -
7B(1)=3`, `Any Hedge Funds=Y`, `Total number of Hedge funds=3`, `Total Gross Assets of
Private Funds=709,905,606.00`, `Count of Private Funds - 7B(2)=0`.

Now that the `advFilingData` feed (Q1/Q2) supplies real per-fund rows, this CSV's
aggregate columns are best read as a **useful cross-check/reconciliation signal**
(e.g. "does the fund count derived from `advFilingData` for this firm match its
Firm-Roster aggregate count") rather than the primary source of private-fund
information — but the aggregate signal itself remains real and independently useful for
firm-level filtering/analytics even standalone.

---

## Q4 — Is there a documented schema/data dictionary for the Firm Roster CSV's columns?

Unchanged from the first pass. **No CSV-specific data dictionary exists for the Firm
Roster CSV.** SEC's bulk-data page
(`https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers`)
states directly:

> "The majority of the data fields included in this report are from Form ADV and the
> report's column headings refer to specific questions within Form ADV (e.g. 5B(2) refers
> to Form ADV, Item 5B(2)). Please refer to the Form ADV for a full description of the
> data fields included in this report; the form ADV may be found at
> https://www.sec.gov/files/formadv-part1a_1.pdf."

Correction to this ticket's premise: direct Python `csv` count gives **448 columns** for
the registered-advisers Firm Roster CSV (`...-34622660.CSV`), not ~150 — the
exempt-advisers CSV is the one close to that figure, at **171 columns**
(`...-34622659.CSV`; ERAs only file Form ADV Items 1, 2, 3, 6, 7, 10, 11, per the same
bulk-data page's own note, hence far fewer columns).

For the (different) `advFilingData`/historical-archive relational product that
`adv_bulk_ingest.py` targets: its column headers follow the same Form-ADV-item-numbered
convention (`IA_ADV_Base_A_...csv` header includes `1A`,`1B1`,`5D1a`,`7B`, etc. — same
decode path via the Form ADV Part 1A instructions PDF), and the file/column shape is
additionally the one the parser code was originally written against, so no new dictionary
gap exists there beyond what already existed when that code was authored.

Separately, FINRA/IARD does publish an official XSD + PDF guide for the **XML compilation
feed** (`iard.com/firm-compilation` → `firm_compilation.zip`, 854 KB, dated 2021-10-14/15,
still live) — `IAPDSECBulkFeed.xsd`, `IAPDStateBulkFeed.xsd`, example XML, and a prose PDF
guide. This documents a different product from the CSV (see Q1's product #2) but was
useful as independent schema-level confirmation that this specific feed carries no
per-fund data.

## Files referenced (all fetched/verified 2026-07-24, ephemeral scratchpad copies)

- `https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers`
- `https://www.sec.gov/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia07012026.zip` / `ia07012026-exempt.zip`
- `https://adviserinfo.sec.gov/compilation`, `https://adviserinfo.sec.gov/adv` (SPA shells; real content via app bundle below)
- `https://adviserinfo.sec.gov/main.7005adea37a6f33f.js` (app bundle — API config, route table, both resolver services)
- `https://reports.adviserinfo.sec.gov/reports/CompilationReports/CompilationReports.manifest.json`
- `https://reports.adviserinfo.sec.gov/reports/CompilationReports/IA_FIRM_SEC_Feed_07_23_2026.xml.gz`
- `https://reports.adviserinfo.sec.gov/reports/foia/reports_metadata.json` (the manifest that was missed on the first pass)
- `https://reports.adviserinfo.sec.gov/reports/foia/advFilingData/2026/ADV_Filing_Data_20260601_20260630.zip`
- `https://www.sec.gov/foia-services/frequently-requested-documents/form-adv-data`
- `https://www.sec.gov/files/adv-filing-data-20111105-20241231-part1.zip` / `-part2.zip`
- `https://reports.adviserinfo.sec.gov/reports/ADV/1588/PDF/1588.pdf`
- `https://www.iard.com/firm-compilation` → `https://iard.com/firm-compilation` → `https://iard.com/sites/iard/files/standalonefiles/firm_compilation.zip`
- `https://www.sec.gov/files/formadv-part1a_1.pdf` (Form ADV Part 1A instructions, cited by SEC's own bulk-data page)
