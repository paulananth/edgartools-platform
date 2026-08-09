# 09 — Office/Disclosure Bulk-Parser Extension Spec

Type: grilling
Status: resolved
Blocked by: none
Blocks: none

## Question

Ticket 07 (research, resolved) confirmed the bulk `advFilingData` archive
already carries real per-office data (`IA/ERA_Schedule_D_1F`, 13,109/214
rows in the June 2026 delta) and real per-event disclosure/DRP data (4 file
families x IA/ERA: `DRP_Criminal`, `DRP_Regulatory`, `DRP_Civil_Judicial`,
`DRP_Advisory_Affiliates`), all joining cleanly on the existing `FilingID`
key -- but left implementation (parsing these files, synthesizing
`accession_number`, wiring into `sec_adv_office`/`sec_adv_disclosure_event`)
explicitly out of scope as a research-only ticket. It also flagged the
schema-shape question (existing tables keyed on
`(accession_number, {office_index,event_index})`, not `filing_id`) without
resolving it.

Separately: `EDGARTOOLS_GOLD.ADVISER_DISCLOSURES` (the gold dynamic table
downstream of `sec_adv_disclosure_event`) has been sitting at 0 rows since
the 2026-08-07 Snowflake account rebuild -- surfaced as a go-live blocker
during Stage 15 of the `snowflake-account-cutover` map
(`.scratch/snowflake-account-cutover/issues/08-six-empty-gold-tables-followup.md`).
Investigating that blocker found the root cause is exactly this
already-known, already-researched gap: nothing in the production ADV
ingestion path (`adv_bulk_ingest.py`, the only ADV parser actually wired
into `load_history`/`daily_incremental` -- the EDGAR-native per-filing
parser in `parsers/adv.py` is confirmed dead code, never invoked from any
deployed pipeline) writes to `sec_adv_disclosure_event` at all.

This ticket turns ticket 07's research into an implementation-ready spec:
exact schema shape, normalization strategy, and scope, closing both the
original ADV-pipeline gap and the go-live blocker in one implementation
pass.

## Answer

Grilled with the user across 4 rounds (2026-08-09), one question at a time,
with cardinality fact-checked against the real archive before locking the
affiliate-table design. All decisions final; no open branches remain.

### 1. Silver schema depth

**`sec_adv_disclosure_event`: extend to capture the rich fields** the
archive actually offers -- narrative summary, monetary amount, sanction
flags/detail, dates, status/resolution, case number -- not just the
existing narrow `disclosure_category`/`event_date`/`is_reported`/
`description` columns. A disclosure with no narrative/sanction/monetary
data is close to useless as a "disclosure," and the data is already in the
CSV at zero extra fetch cost.

**`sec_adv_office`: keep the existing columns as the primary/required
set** (`office_name`/`city`/`state_or_country`/`country`/
`is_headquarters`) -- the richer fields the archive offers (branch number,
employee count, business-line flags) are less clearly gold-worthy and are
covered anyway by the raw-fields catch-all below if a future consumer
needs them.

### 2. Gold model follow-through

**In scope, same spec.** `infra/snowflake/dbt/edgartools_gold/models/gold/adviser_disclosures.sql`
gets the new silver columns added through to gold (currently:
`fact_key, company_key, date_key, disclosure_category_key,
accession_number, event_index, is_reported` -- missing any
description/summary/monetary field entirely). This is a direct, mechanical
consequence of the silver schema decision above, not a new design
question -- the model already does a fixed-column `select` from the
source table.

### 3. Bulk vs. EDGAR-native source precedence

**Moot.** Confirmed via code search this session: the EDGAR-native
per-filing parser (`edgar_warehouse/parsers/adv.py`'s `parse_adv()` /
`_run_parse_adv_bronze` in `warehouse_orchestrator.py`) is reachable only
via the standalone `parse-adv-bronze` CLI subcommand, which does not
appear anywhere in `infra/scripts/deploy-aws-application.sh` -- no Step
Functions state calls it. Zero rows have ever been written to
`sec_adv_office`/`sec_adv_disclosure_event` by any production pipeline.
No merge/precedence strategy is needed since there is nothing to conflict
with; flagging this explicitly in the spec so a future reader doesn't
assume one is needed.

### 4. Normalizing 4 heterogeneous DRP file schemas

**Common column set + raw-fields catch-all column.** The 4 DRP file
families (Criminal: 11.A/11.B columns; Regulatory: 11.C-G, `Principal
Sanction`, `Monetary Amount`; Civil/Judicial: 11.H, `Relief Sought`, `Court`)
share a common core -- `event_date`, `status`, `resolution`,
`monetary_amount`, a synthesized `sanction_summary` bool/string, and the
free-text `Summary` field -- normalized into fixed columns on
`sec_adv_disclosure_event`. Additionally, every row also gets a raw
JSON/variant column preserving every source column verbatim, so
type-specific nuance (e.g. `Case Number` for regulatory, `Court` for
civil) isn't lost even though it's not promoted to its own column. Matches
this repo's existing provenance-column pattern
(`source_format`/`parser_version`) and avoids a second archive-parsing
pass if a future need discovers the common set was insufficient.

### 5. `disclosure_category` value mapping

**Locked: `"criminal"`, `"regulatory"`, `"civil_judicial"`** -- one value
per DRP file family, matching the file names directly rather than
inventing a new taxonomy. Traceable straight back to source.

### 6. Advisory_Affiliates linkage cardinality and modeling

**Fact-checked against the real June 2026 archive before deciding** (not
assumed): `IA_DRP_Advisory_Affiliates` (4,242 rows) has only 3,802 unique
`(FilingID, ReferenceID)` pairs -- 456 of 3,338 unique `ReferenceID`s
(13.7%) have more than one affiliate row. Real example: a single Regulatory
Action (`ReferenceID=1788983`) filed against both "HSBC HOLDINGS PLC" and
"HSBC NORTH AMERICA HOLDINGS INC." as two separate affiliate rows. The ERA
file shows the same shape (5 of 73 unique `ReferenceID`s multi-affiliate,
one Civil Judicial Action against 4 individually-named affiliates). This
is **not** a 1:1 relationship, so inline columns on
`sec_adv_disclosure_event` would either drop rows or silently duplicate
the parent event.

**Decision: new silver table, `sec_adv_disclosure_affiliate`.** One row
per affiliate-linkage: `accession_number` (synthesized `iapd-adv:{filing_id}`,
matching the parent disclosure event's own synthesis pattern),
`reference_id`, `affiliate_index` (ordinal within the `(FilingID,
ReferenceID)` group, since a single reference can have multiple affiliate
rows), `affiliate_name`, `affiliate_crd`, `affiliate_type`,
`is_registered`. Joins back to `sec_adv_disclosure_event` via
`(accession_number, reference_id)`.

**Gold-layer exposure for this new table: explicitly out of scope for
this spec.** Ticket 08's actual go-live blocker (`ADVISER_DISCLOSURES`
empty) is fixed without a new gold table for affiliates; a gold view for
affiliate-level detail is a legitimate future ask but isn't demanded by
anything currently blocked.

### 7. Accession-number and ordinal synthesis (carried from ticket 07)

Confirmed viable, now locked as the implementation pattern: synthesize
`accession_number = f"iapd-adv:{filing_id}"` for bulk-sourced office and
disclosure rows (mirroring `adv_bulk_ingest.py:151`'s existing pattern for
`sec_adv_filing`/`sec_adv_private_fund`), so bulk-sourced rows share the
same primary-key shape as (dead-code-path) EDGAR-sourced rows with no
schema change to the existing tables' primary keys. `office_index`
derives from `(FilingID, Branch Number)` ordinal position;
`event_index`/disclosure ordinal derives from `(FilingID, ReferenceID)`
position within the parsed DRP rows for that filing.

### 8. Backfill scope for already-ingested months

**Reprocess already-ingested archives, not prospective-only.** The
already-fetched monthly ZIPs are sitting in S3 bronze
(`iapd_adv_bulk/YYYY-MM/`) at zero additional SEC-fetch cost.
`ingest_adv_bulk_archive` is already idempotent/re-runnable (its
`merge_adv_filings`/`merge_adv_private_funds` upsert pattern), so
extending it to also read the 6 new file families and re-running it
against the already-fetched archives for the current rolling window
(ticket 03's decided 13-month window, no 2000-2024 historical backfill --
unaffected by this ticket) naturally backfills office/disclosure data for
those months as a side effect of the same idempotent function, with no
separate backfill mechanism needed. Rejected leaving past months silently
without office/disclosure data -- that would make `ADVISER_DISCLOSURES`
"look populated" while actually missing months of real coverage with no
visible signal anything's wrong.

### 9. Testing shape

**Real downloaded archive fixtures, not hand-rolled synthetic CSVs.**
Matches this repo's own documented lesson (CLAUDE.md's `sec_company`/
`entity_name` incident: "a hand-rolled stub that encodes a query's
expected shape can silently drift from the real schema... prefer a
schema-backed fixture... over a string-matched stub"). Reinforced by this
session's own experience inspecting the real archive: it is **not** pure
UTF-8 (latin-1-decodable, not always cleanly UTF-8), has variable column
counts across file families, and real quoting/escaping behavior a
hand-typed fixture would be unlikely to reproduce by accident. Tests
should use trimmed real ZIP fixtures or CSV rows extracted verbatim from a
real downloaded archive (e.g. the June 2026
`ADV_Filing_Data_20260601_20260630.zip` already fetched this session),
not synthetic data -- even though ticket 07 already fully documented the
exact real headers, a hand-typed fixture built from that documentation is
still a second-hand copy that can drift.

## Summary of new/changed schema

**`sec_adv_disclosure_event` (extended):** existing columns plus
`monetary_amount`, `resolution`, `status`, `case_number` (nullable,
regulatory-only), `raw_fields` (JSON/variant, full source row verbatim).

**`sec_adv_disclosure_affiliate` (new table):** `accession_number`,
`reference_id`, `affiliate_index`, `affiliate_name`, `affiliate_crd`,
`affiliate_type`, `is_registered`.

**`sec_adv_office`:** unchanged column set; parser extension only (new
source: `Schedule_D_1F`, not currently read).

**`EDGARTOOLS_GOLD.ADVISER_DISCLOSURES` (dbt model):** add the new
promoted columns from `sec_adv_disclosure_event` (description/summary,
monetary_amount, resolution, status) through to gold, mirroring the
existing `select`-from-source shape.

**`adv_bulk_ingest.py`:** extend `parse_adv_bulk_archive`/
`ingest_adv_bulk_archive` to also read `IA/ERA_Schedule_D_1F` (office),
`IA/ERA_DRP_Criminal/Regulatory/Civil_Judicial` (disclosure events), and
`IA/ERA_DRP_Advisory_Affiliates` (affiliate linkage) -- same `FilingID`
join key, same `iapd-adv:{filing_id}` accession-number synthesis pattern
already used for filings/funds.
