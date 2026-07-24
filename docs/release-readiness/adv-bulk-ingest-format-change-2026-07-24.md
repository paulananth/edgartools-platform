# ADV Bulk Ingest: SEC Changed the IAPD Bulk Data Format

## Status: BLOCKED — parser rewrite needed before ADV can flow to MDM/Neo4j

## Context

Operator asked to load ADV data end-to-end (fetch → silver → MDM → Neo4j graph)
and wire it into `daily_incremental` + `load_history`. Per-`git log` this repo
already has the full downstream chain built and working:

```
ingest-relationship-sources --kind iapd_adv_bulk   (edgar_warehouse/application/adv_bulk_ingest.py)
  -> sec_adv_filing / sec_adv_office / sec_adv_disclosure_event / sec_adv_private_fund (silver)
  -> mdm run --entity-type adviser / --entity-type fund
  -> mdm derive-relationships   (MANAGES_FUND etc.)
  -> mdm sync-graph -> mdm verify-graph (--skip-native-app) -> mdm graph-activate -> mdm verify-graph
```

The only genuinely missing piece was an automated **fetch** step — nothing in
this repo downloads IAPD bulk data itself; `parse-adv-bronze` and
`ingest-relationship-sources --kind iapd_adv_bulk` both require an operator to
have already staged the artifact.

## What was verified (2026-07-24)

**SEC's live IAPD bulk data page** (`https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers`
— fetched with `curl -A "EdgarTools Platform thepaulananth@gmail.com"`; a
generic User-Agent gets `403`) confirms:

- Bulk data is a **monthly full snapshot**, two separate ZIPs per month:
  Registered Investment Advisers and Exempt Reporting Advisers (e.g.
  `ia07012026.zip` / `ia07012026-exempt.zip` for July 2026). No year-window
  concept applies — each file is the current point-in-time roster.
- No auth required for download, but filenames are **not** fully predictable
  month to month (`ia060126_0.zip` has a stray `_0`, `ia020226-exemptzip.zip`
  uses `-exemptzip` instead of `-exempt`) — a fetcher must scrape the listing
  page for the current month's links, not construct a URL from the date.
- File sizes are small (July 2026: 5.27 MB registered, 0.84 MB exempt) — safe
  to fetch directly, no need to run inside AWS/ECS the way the 712 MB
  `silver.duckdb` did.

**Downloaded both July 2026 files and inspected their contents directly**
(not just headers) — and this is the actual blocker:

- `adv_bulk_ingest.py`'s `_rows()` looks for files matching
  `(?:IA|ERA)_ADV_Base(?:_A)?_[^/]*\.csv$`,
  `(?:IA|ERA)_Schedule_D_7B1_[^/]*\.csv$`,
  `(?:IA|ERA)_Schedule_D_7B2_[^/]*\.csv$`, `ADV_Filing_Types_[^/]*\.csv$` —
  this is the **old normalized/relational IAPD bulk archive** shape (one file
  per Form ADV schedule).
- The **actual current archive** contains exactly one file:
  `IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_<id>.CSV` (registered) /
  `IA_SEC_-_FIRM_ROSTER_FOIA_DOWNLOAD_-_<id>.CSV` (exempt) — a single flat
  "Firm Roster" file with ~150 columns keyed directly to Form ADV item numbers
  (`1I`, `2B(1)`, `3A`, `3A-Other`, `6A(1)`–`7A(16)`, `7B`, ...).
- None of the parser's filename regexes match this file, so
  `ingest_adv_bulk_archive` would **silently return zero rows** (`_rows()`
  returns `[]` on no match; nothing raises) rather than error loudly — this
  would have looked like a successful, uneventful no-op run if executed
  without first inspecting the archive contents.
- **Private funds are the harder problem, not just a filename fix.** The old
  Schedule D 7B1/7B2 files gave one row per private fund (name, CRD,
  jurisdiction, AUM — what `AdvBulkFund`/`sec_adv_private_fund` expect). The
  new Firm Roster only has **firm-level aggregate counts** — "Total number of
  Hedge funds", "Any PE Funds", "Count of Private Funds - 7B(1)" — not
  individual fund records. It is not yet confirmed whether SEC still publishes
  per-fund private-fund detail anywhere in bulk form, or whether that detail
  is now IAPD-website-only (per-adviser lookup, not bulk).

## What is NOT blocked

- The fetch mechanism itself (scrape IAPD page → download → SHA-256 → stage to
  S3 → build `ingest-relationship-sources` manifest) is straightforward and
  unblocked — this doc's research already nails down the exact URLs/pattern.
- `mdm run` / `mdm derive-relationships` / `mdm sync-graph` /
  `mdm verify-graph` / `mdm graph-activate` are all working, tested commands
  (validated again this session against the live Ticket 20 graph work) — they
  just need real ADV silver rows to operate on.

## Required next steps (in order)

1. **Confirm scope of the format change** — check whether SEC still publishes
   the old relational archive anywhere (a different URL/product), or whether
   Firm Roster is now the only bulk product. Check IAPD's own site
   (`adviserinfo.sec.gov`) for a separate "Private Funds" bulk download if one
   exists — Form ADV Part 1A Schedule D 7B is filed data that must live
   *somewhere* in bulk form, even if not in this particular ZIP.
2. **Rewrite (or add a second code path to) `adv_bulk_ingest.py`** to parse the
   Firm Roster CSV format directly into `sec_adv_filing` / `sec_adv_office` /
   `sec_adv_disclosure_event` (these three don't need per-fund granularity —
   firm identity, office, and disclosure-event data likely map cleanly from
   Firm Roster columns). Decide how (or whether) to populate
   `sec_adv_private_fund` given the aggregate-only counts — options: (a) store
   only aggregate counts and redefine what that table represents, (b) find the
   real per-fund bulk source, (c) mark private-fund-detail as unavailable at
   bulk scale and rely on `parse-adv-bronze`'s EDGAR-native-filed ADV path for
   funds that also happen to be public filers.
3. **Manual end-to-end validation** (do this before automating fetch): stage
   the two July 2026 files to S3, hand-build a source manifest, run
   `ingest-relationship-sources` as an ECS task (needs the 712 MB
   `silver.duckdb` — must run in AWS, same lesson as the Ticket 20 freeze
   rebuild this session), confirm `sec_adv_filing`/`sec_adv_office` counts jump
   from ~1 to thousands, then `mdm run --entity-type adviser --entity-type
   fund` → `mdm derive-relationships` → `mdm sync-graph` → `mdm verify-graph
   --skip-native-app` → `mdm graph-activate` → final `mdm verify-graph`,
   confirming real adviser/fund nodes and `MANAGES_FUND` edges appear in the
   graph (not just the placeholder 112/1 counts).
4. **Only then** build the automated fetch step and wire it into
   `load_history` (one-time baseline fetch-latest) and `daily_incremental`
   (idempotent monthly-cadence check — `dataset_period` should be the
   idempotency key; verify `ingest_adv_bulk_archive` skips cleanly on a
   repeat `dataset_period` before wiring into a *daily* job, or it will
   re-download and re-ingest the full adviser universe every day for a
   monthly-cadence source).

## Session artifacts (ephemeral — will need re-downloading)

Both July 2026 zips were downloaded to this session's scratchpad only, not
committed or uploaded to S3:
`/private/tmp/claude-501/.../scratchpad/ia07012026.zip` (registered, 5.27 MB)
`/private/tmp/claude-501/.../scratchpad/ia07012026-exempt.zip` (exempt, 0.84 MB)

Re-fetch with (no auth needed, but User-Agent required or SEC returns 403):

```bash
UA="EdgarTools Platform thepaulananth@gmail.com"
BASE="https://www.sec.gov/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers"
curl -A "$UA" "$BASE/ia07012026.zip" -o ia07012026.zip
curl -A "$UA" "$BASE/ia07012026-exempt.zip" -o ia07012026-exempt.zip
```

(Filenames for the *current* month should be re-discovered from the listing
page, not assumed — see "not fully predictable" above.)
