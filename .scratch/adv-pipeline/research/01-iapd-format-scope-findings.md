# Research: Scope of the IAPD Bulk Format Change

Ticket: `.scratch/adv-pipeline/issues/01-confirm-scope-of-iapd-format-change.md`
Date: 2026-07-24
Method: primary sources only — SEC.gov, adviserinfo.sec.gov (IAPD), iard.com (FINRA,
operator of IAPD), and actual files downloaded and inspected byte-for-byte. All SEC.gov
fetches used `curl -A "EdgarTools Platform thepaulananth@gmail.com"` (a generic
User-Agent gets 403). All files referenced below were re-downloaded this session to
`/private/tmp/claude-501/.../scratchpad/iapd/` (ephemeral — re-fetch commands included).

## Summary answer

1. **The Firm Roster CSV is, for practical purposes, the only *current* bulk product.**
   A separate relational/Schedule-D-detail bulk product **used to exist** and is still
   downloadable, but it is a frozen historical archive capped at 2024-12-31 — not a live
   feed. SEC's own FOIA page states that current (2025-01-01–present) data lives at
   `adviserinfo.sec.gov/adv`, and that page resolves to the *same* three IAPD
   "Compilation Report" feeds reachable from `adviserinfo.sec.gov/compilation` — which
   contain **no per-fund records at all**, confirmed against the official XSD schema.
2. **No, per-fund Schedule 7.B.(1)/(2) detail is not obtainable at scale for anything
   post-2024-12-31.** It is only obtainable per-adviser, via IAPD's per-firm PDF report
   (confirmed populated with real fund names/PFIDs) — genuinely not bulk-ingestible
   (one HTTP fetch per CRD, ~23,600 SEC-registered+exempt firms, no bulk index of which
   CRDs to fetch beyond the roster itself).
3. **Yes** — the Firm Roster CSV's aggregate columns are real, populated data (not
   placeholders), and support at minimum: presence/absence of private-fund management,
   and per-type counts (hedge/PE/VC/real-estate/securitized/liquidity/other) plus total
   gross private-fund assets, all at firm granularity.
4. **No roster-specific data dictionary exists for the CSV.** SEC's bulk-data page
   explicitly tells readers to consult the generic Form ADV Part 1A instructions PDF for
   column meanings — there is no CSV-specific field-by-field document. A **different**
   product (the discontinued-for-CSV-purposes XML "Compilation Report" feed) does have
   an official XSD schema + PDF guide, still hosted live by FINRA/IARD, and it doubles as
   independent proof for Q1/Q2 (its `Item7BType` has no per-fund child elements).

---

## Q1 — Is the Firm Roster CSV SEC's only bulk product, or does a separate relational/Schedule-D-detail product exist elsewhere?

### What adviserinfo.sec.gov actually is, and why curling it looks empty

`https://adviserinfo.sec.gov/compilation` is an Angular SPA — `curl` returns a 9 KB HTML
shell with zero data (`compilation.html`, this session). The real content is fetched
client-side. Reading the app bundle
(`https://adviserinfo.sec.gov/main.7005adea37a6f33f.js`, fetched directly with curl,
1.3 MB minified JS) reveals the SPA's own internal API config:

```
"reports":"https://reports.adviserinfo.sec.gov"
"classic-reports":"https://files.adviserinfo.sec.gov"
```

and the route table:

```
{path:"compilation", ..., page: INVESTMENT_ADVISOR_DATA}
{path:"adv", ..., page: FIRM_FORM_ADV}
```

Critically, **both** the `/compilation` and `/adv` routes resolve their page data via the
identical `foiaReportService.getCompilationReport()` call in the bundle — they are two
different labels/landing pages ("Investment Adviser Data" vs. "Form ADV Data") over the
**same underlying feed manifest**, not two different datasets.

### The manifest itself

`getCompilationReport()` fetches:

```
https://reports.adviserinfo.sec.gov/reports/CompilationReports/CompilationReports.manifest.json
```

Fetched directly this session:

```json
{"files": [
  {"name": "IA_FIRM_SEC_Feed_07_23_2026.xml.gz", "size": "78 MB", "date": "07/23/2026"},
  {"name": "IA_FIRM_STATE_Feed_07_23_2026.xml.gz", "size": "69 MB", "date": "07/23/2026"},
  {"name": "IA_INDVL_Feed_07_23_2026.xml.zip", "size": "167 MB", "date": "07/23/2026"}
]}
```

Three feeds only: SEC-registered firms, state-registered firms, individuals (IARs). **No
private-fund/Schedule-D feed appears in this manifest.** This is the full, current
inventory of IAPD's own official bulk data — confirmed directly from the compiled app's
API config, not inferred from page text.

### Downloaded and inspected `IA_FIRM_SEC_Feed_07_23_2026.xml.gz`

`curl`'d directly (7.2 MB gzip → 81.6 MB XML, 23,602 `<Firm>` records — consistent with
the CSV bulk page's ~17,073 registered + ~6,535 exempt ≈ 23,608, confirming both are the
same underlying universe in different shapes). Sample record for a firm with private
funds:

```xml
<Item7B Q7B="Y"/>
```

`Item7B` is a **self-closing element with a single Y/N attribute and no children** —
confirmed by grepping the entire 81 MB file: 12,577 firms have `Q7B="Y"`, and the string
"Fund" appears only 83 times total across the whole file, exclusively inside unrelated
`<WebAddr>` URLs (e.g. a firm's own marketing links containing the word "fund"). **Zero**
per-fund sub-records, and — unlike the CSV — **not even the aggregate hedge/PE/VC counts**
are present in this XML feed. The XML feed is strictly less detailed than the CSV Firm
Roster for private funds.

This is independently confirmed by the official schema (see Q4): `Item7BType` in
`IAPDSECBulkFeed.xsd` declares exactly one attribute, `Q7B` (Y/N/null), full stop.

### The FOIA page — the "FOIA_DOWNLOAD" clue

The Firm Roster CSV's own filename
(`IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622660.CSV`) points to SEC's FOIA program.
Fetched `https://www.sec.gov/foia-services/frequently-requested-documents/form-adv-data`
directly (linked from the app bundle's external-link list, confirming it's the correct
FOIA page — 200 OK, ~85 KB HTML). Key text (verbatim, HTML-stripped):

> "Form ADV Data from January 1, 2025, to present is available on the Investment Adviser
> Public Disclosure website (https://adviserinfo.sec.gov/adv). For historical data prior
> to January 1, 2025, Form ADV Part 1 and Form ADV-W Data Files for SEC registered
> investment advisers and for SEC exempt reporting advisers is available in .csv format,
> below. These data sets consist of multiple tables that may need to be combined into a
> database or linked, depending on how the data will be used."

This is the smoking gun: **SEC explicitly discontinued the old multi-table relational CSV
format as a live product on 2025-01-01**, and its own page tells readers that "current"
data now lives at `adviserinfo.sec.gov/adv` — which (per the SPA analysis above) is the
same sparse 3-feed XML manifest, not a richer replacement.

The page's historical archive is two ZIPs:
`https://www.sec.gov/files/adv-filing-data-20111105-20241231-part1.zip` (confirmed via a
byte-range HTTP request against the live 429 MB file, no full download needed) and
`...-part2.zip` (428.9 MB, `content-length` header confirmed). Inspecting the ZIP local
file headers via range requests (no full download) shows the *exact* old relational shape
`edgar_warehouse/application/adv_bulk_ingest.py` was written against:

```
part1: adv-filing-data-20111105-20241231-part1/ADV_Filing_Types_20111105_20241231.csv
part2 (central directory, fetched via a range request on the last 200 KB of the file):
  IA_Schedule_D_10A_20111105_20241231.csv
  IA_Schedule_D_2A_20111105_20241231.csv
  IA_Schedule_D_7B1_20111105_20241231.csv          <- per-fund detail, confirmed present historically
  IA_Schedule_D_7B2_20111105_20241231.csv          <- per-fund detail, confirmed present historically
  IA_Schedule_D_9C_20111105_20241231.csv
  IA_Schedule_D_Books_and_Records_20111105_20241231.csv
  ... (41 Schedule_D/Schedule_R files total)
```

So the relational, per-fund-row `IA_Schedule_D_7B1`/`7B2` format **did exist and is
literally still downloadable** — but it is a fixed, closed, historical snapshot dated
`20111105-20241231`. There is no evidence anywhere (FOIA page, IAPD SPA API config,
compilation manifest, or the CSV bulk page) that SEC has continued producing per-fund
relational files past 2024-12-31.

**Contradiction worth flagging:** the CSV bulk-data page
(`https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers`)
itself says "Historical ADV filing data ... from January 2001 through the most recent
quarter is available in .csv format at Form ADV Data" — but the FOIA page it links to
caps its historical relational ZIPs at 2024-12-31 and explicitly redirects post-2025 data
elsewhere. SEC's own cross-links are stale/inconsistent on this point; don't trust "most
recent quarter" language at face value without checking the actual file, as this session
(and last session, discovering the CSV format itself) both had to do.

**Conclusion for Q1:** Firm Roster CSV (sec.gov bulk page) and the 3-feed XML compilation
report (adviserinfo.sec.gov, both `/compilation` and `/adv` routes) are SEC's only two
*live* bulk products, and they cover the same firm universe with the CSV being the richer
of the two for private-fund aggregates. No separate current relational/Schedule-D-detail
bulk product exists under any URL found — the one that used to exist is closed and frozen
at 2024-12-31.

---

## Q2 — Is per-fund Schedule 7.B.(1)/(2) detail obtainable any other way at scale, or is per-adviser lookup genuinely the only remaining route?

**Per-adviser lookup is the only remaining route for anything filed after 2024-12-31, and
it does not scale to bulk ingestion.**

Confirmed by fetching a real per-adviser PDF report directly:
`https://reports.adviserinfo.sec.gov/reports/ADV/1588/PDF/1588.pdf` (CRD 1588, Davenport &
Company LLC — chosen because the Firm Roster CSV shows this firm has 3 hedge funds and
$709.9M in private fund assets, per Q3 below). Downloaded (2.17 MB), converted with
`pdftotext` (required installing `poppler` via `brew install poppler` — not present in
this environment initially), and inspected. The PDF contains the **full populated
Schedule D Section 7.B.(1)** for each private fund, e.g.:

```
Information About the Private Fund
1. (a) Name of the private fund:
   EWF PARTNERS II LLC
   (b) Private fund identification number:
   805-4154444394
2. Under the laws of what state or country is the private fund organized:
   State: Virginia
10. What type of fund is the private fund? hedge fund
11. Current gross asset value of the private fund: [populated]
```

This is real, current, per-fund data (name, PFID, jurisdiction, fund type, AUM) — the
exact fields `AdvBulkFund`/`sec_adv_private_fund` need. It **exists** and is **current**.
It is simply not distributed in bulk: this is one 2.2 MB PDF fetch for one firm. To
reconstruct what the old `IA_Schedule_D_7B1`/`7B2` bulk files provided, an ingester would
need one HTTP fetch per CRD across the entire ~23,600-firm roster (and re-fetch on every
refresh cycle to catch changes) — no API, no bulk endpoint, no index of "which CRDs have
private funds" beyond the roster's own aggregate flag (which at least narrows the set to
the ~5,970 CRDs with `7B="Y"`, see Q3). This is a scale/engineering problem, not a
data-availability problem — the data exists per-adviser but there is no SEC/IAPD/FINRA
bulk product carrying it.

No other route was found: the IAPD SPA bundle's route table (`main.7005adea37a6f33f.js`)
enumerates only `compilation`, `adv` (both resolving to the same 3-feed manifest),
`individual/summary`, and `resources` — no private-fund-specific bulk route exists in the
app's own routing configuration.

---

## Q3 — Do the Firm Roster CSV's aggregate private-fund columns carry usable signal even without per-fund identity?

**Yes, verified against real, populated data**, not just column-name inference.

Parsed `IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622660.CSV` (registered advisers,
17,073 rows) with Python's `csv` module (447 data columns after the header). Scanning the
first 16,935 data rows for the relevant columns:

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

Full 7B set of sub-type columns confirmed present (13 real columns, not counting
"Any"/count pairs individually): Hedge, Liquidity, PE, Real Estate, Securitized, VC,
Other — each with both a Y/N flag and a numeric count, plus `Any PFs a Master` and
`Total Gross Assets of Private Funds`.

Sample real row (Davenport & Company LLC, CRD 1588):

```
7B = Y
Count of Private Funds - 7B(1) = 3
Any PFs a Master = N
Any Hedge Funds = Y
Total number of Hedge funds = 3
Any PE Funds = N
Total number of PE funds = (blank)
Total Gross Assets of Private Funds = 709,905,606.00
Count of Private Funds - 7B(2) = 0
```

This supports, at firm granularity: (a) binary "manages private funds" flag usable as a
graph node property or filter; (b) per-fund-type counts (hedge/PE/VC/liquidity/real
estate/securitized/other) usable for aggregate analytics ("how many hedge-fund-managing
advisers are there"); (c) total private-fund AUM per firm. It cannot support anything
requiring individual fund identity (PFID-keyed `MANAGES_FUND` edges per
`adviser-fund-source-contract.md`) — there is no fund-level row to key off of.

---

## Q4 — Is there a documented schema/data dictionary for the Firm Roster CSV's columns?

**No CSV-specific data dictionary exists.** The bulk-data page itself
(`https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers`,
re-fetched this session) states directly:

> "The majority of the data fields included in this report are from Form ADV and the
> report's column headings refer to specific questions within Form ADV (e.g. 5B(2) refers
> to Form ADV, Item 5B(2)). Please refer to the Form ADV for a full description of the
> data fields included in this report; the form ADV may be found at
> https://www.sec.gov/files/formadv-part1a_1.pdf."

So the decode path is real and primary-source (Form ADV Part 1A + its instructions), but
it is generic Form-ADV documentation, not a roster-CSV-specific dictionary mapping each of
the CSV's ~448 (registered) / 171 (exempt) header strings to a description. Note: the
ticket's estimate of "~150 columns" undercounts the registered-firm file — this session's
direct count (Python `csv` reader) is **448 columns for the registered-advisers CSV**
(`IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_34622660.CSV`) and **171 columns for the
exempt-reporting-advisers CSV** (`...-34622659.CSV`, matching the note on the bulk-data
page that ERAs only file Items 1, 2, 3, 6, 7, 10, 11 — a strict subset of items, hence
fewer columns). The "~150" figure in the ticket appears to describe the exempt file, not
the registered one; parser work (ticket 02) should size against both, since
`adv_bulk_ingest.py` handles both `IA_` and `ERA_` file families.

**A genuine, roster-adjacent schema does exist, just for the discontinued-CSV/XML side of
the product, not the CSV itself.** FINRA (which operates IARD/IAPD) hosts
`https://iard.com/firm-compilation` (redirect target of `https://www.iard.com/firm-compilation`,
the exact URL embedded in the adviserinfo.sec.gov app bundle as `firmXmlSchemaUrl`),
which serves `firm_compilation.zip` (854 KB, fetched directly this session). Contents:

```
firm_compilation/Compilation Report PD_XML_Guide.pdf   (1.26 MB — prose field guide)
firm_compilation/EXAMPLE_IA_SEC.xml
firm_compilation/EXAMPLE_IA_STATE.xml
firm_compilation/IAPDSECBulkFeed.xsd                     (131 KB — full XSD schema)
firm_compilation/IAPDStateBulkFeed.xsd                   (145 KB)
```

This is an official, documented, machine-readable schema for the XML compilation feed
(the one this session confirmed at `IA_FIRM_SEC_Feed_07_23_2026.xml.gz`) — every
`ItemXXType` complex type is present with `xsd:documentation` annotations. It directly
confirms Q1/Q2's finding rather than merely asserting it: `Item7BType` is declared as:

```xml
<xsd:complexType name="Item7BType">
  <xsd:attribute name="Q7B" type="answerYNType" use="optional">
    <xsd:annotation><xsd:documentation xml:lang="en">
      This node has Firm's response to Part1A Item 7B-Are you an adviser to any
      private fund (Y/N/null).
    </xsd:documentation></xsd:annotation>
  </xsd:attribute>
</xsd:complexType>
```

One attribute, no children, no aggregate counts, no per-fund elements — authoritative,
schema-level confirmation (not just an empirical grep of one XML file) that this feed
carries no fund-level or fund-count data whatsoever. The zip's file timestamps read
2021-10-14/15, so this schema package predates the 2025 CSV/relational-format cutover —
it documents the format that was already live in 2021 and still is; it does not describe
the newer Firm Roster CSV, which is a separate, sec.gov-hosted product with its own
(undocumented) column set.

## Files referenced (all fetched/verified 2026-07-24, ephemeral scratchpad copies)

- `https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers`
- `https://www.sec.gov/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia07012026.zip`
- `https://www.sec.gov/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/ia07012026-exempt.zip`
- `https://adviserinfo.sec.gov/compilation` (SPA shell; real content via app bundle below)
- `https://adviserinfo.sec.gov/main.7005adea37a6f33f.js` (app bundle — API config, route table)
- `https://reports.adviserinfo.sec.gov/reports/CompilationReports/CompilationReports.manifest.json`
- `https://reports.adviserinfo.sec.gov/reports/CompilationReports/IA_FIRM_SEC_Feed_07_23_2026.xml.gz`
- `https://www.sec.gov/foia-services/frequently-requested-documents/form-adv-data`
- `https://www.sec.gov/files/adv-filing-data-20111105-20241231-part1.zip`
- `https://www.sec.gov/files/adv-filing-data-20111105-20241231-part2.zip`
- `https://reports.adviserinfo.sec.gov/reports/ADV/1588/PDF/1588.pdf`
- `https://www.iard.com/firm-compilation` → `https://iard.com/firm-compilation`
- `https://iard.com/sites/iard/files/standalonefiles/firm_compilation.zip`
- `https://www.sec.gov/files/formadv-part1a_1.pdf` (Form ADV Part 1A instructions, cited by SEC's own bulk-data page)
