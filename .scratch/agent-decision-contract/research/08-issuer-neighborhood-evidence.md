# Ticket 08 — Issuer neighborhood evidence inventory

Live inventory of Trading-Relevant Neighborhood evidence for issuer Subject
Bundle Read. Not a reopen of predecessor
[agent-decision-data-plane/08](../../agent-decision-data-plane/issues/08-snowflake-export-issuer-evidence.md)
(closed as *intent*: export registry includes the three silver evidence
tables). This file records where those tables, plus holdings and insider
ownership, actually live after ADR 0006 and current gold/source/silver
wiring.

Queried 2026-09-10 against `EDGARTOOLS_PROD` via SnowCLI connection
`edgartools-prod`. Counts only; no secret values. DuckDB canonical
`silver.duckdb` was not hydrated from S3 in this pass — DuckDB presence is
schema/writer inventory, not a live row count.

## Verdict

| Neighborhood section | Canonical evidence today | On Snowflake export/manifest path? | Live prod rows (collapsed silver unless noted) | Agent-grade bind as of this inventory |
| --- | --- | --- | --- | --- |
| Auditor / `AUDITED_BY` | `sec_auditor_report_evidence` (DuckDB + SILVER). No gold table. SOURCE passthrough exists and is empty. | Yes — SOURCE passthrough | SOURCE/SILVER/LANDING **0**. Graph `AUDITED_BY` **0**. Gold `ACCOUNTING_FLAGS` **0**. | Table exists; **no rows**. Sketch reads SOURCE (correct layer, empty). |
| Employment / `EMPLOYED_BY` | Item 5.02 `sec_employment_event` + DEF 14A `sec_executive_record`. Graph edges are the neighborhood join. | Yes for events (SOURCE passthrough). Exec records are SOURCE `EXECUTIVE_RECORD` + gold `EXECUTIVE_RECORDS`. | Events: LANDING 11,221 / SILVER+SOURCE 7,676. Exec: 14,755 all layers. Graph `EMPLOYED_BY` **3**. | Evidence tables populated. Graph almost empty. Contract `source_system` names do not match pipeline stamps. |
| Subsidiary / `HAS_PARENT` | `sec_subsidiary_evidence` (DuckDB + SILVER). No gold table. | Yes — SOURCE passthrough | SOURCE/SILVER/LANDING **0**. Graph `HAS_PARENT_COMPANY` **0**. | Table exists; **no rows**. Inventory-complete gate in Python semantics would still mark unavailable even if edges existed. |
| `holders_of_subject` / 13F | Gold `INSTITUTIONAL_HOLDINGS` (from silver `sec_thirteenf_holding`). Filing header `sec_thirteenf_filing` is SILVER-only. | Holdings yes (SOURCE + gold). **Filing table is not on SOURCE export.** | Holdings 6,799,919 SOURCE/SILVER/GOLD. Filings 14,364 SILVER/LANDING. Graph `INSTITUTIONAL_HOLDS` **0**. | Gold table is populated, but **has no `issuer_cik`**. Sketch `BUNDLE_HOLDERS_OF_SUBJECT` cannot bind as written. |
| Insiders / `IS_INSIDER` | Graph `IS_INSIDER` + gold ownership accession. Person/title live on silver `sec_ownership_reporting_owner` (and txns). | Dimensional `OWNERSHIP_HOLDINGS` / `OWNERSHIP_ACTIVITY` yes. Raw owner/txn tables are SILVER landing, not SOURCE. | Silver owners 59,030; non-deriv txn 78,469; deriv txn 2,969. Gold holdings 42,507 / activity 81,438. Graph `IS_INSIDER` **1,617**. | Best-populated neighborhood. Gold ownership **drops `owner_cik` / `owner_name`**; agent-grade join needs graph (or silver owner rows) plus accession. |

`EDGARTOOLS_DECISION` exists in prod and is **empty** (no tables/views). The
SQL sketch in `infra/snowflake/sql/decision_contract/02_subject_bundle_read_issuer.sql`
is not deployed.

---

## Layer map

Write path for the three predecessor-ticket evidence tables:

```text
parser (auditor_evidence / subsidiary_exhibits / Item 5.02 or fundamentals)
  -> DuckDB silver_store.merge_*  (@track_landing_rows)
  -> S3 silver-landing Parquet
  -> LOAD_SILVER_LANDING() COPY INTO EDGARTOOLS_SILVER_LANDING
  -> dbt silver dynamic table collapse -> EDGARTOOLS_SILVER
  -> source_dimensional_export builders (read SILVER, not DuckDB)
  -> S3 serving export Parquet
  -> LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN / LOAD_EXPORTS_FOR_RUN
  -> EDGARTOOLS_SOURCE passthrough tables
```

There is **no dbt gold model** for `sec_auditor_report_evidence`,
`sec_subsidiary_evidence`, or `sec_employment_event`. Comment in
`edgar_warehouse/serving/source_dimensional_export.py` (`_fetch_snowflake_silver_arrow`)
calls them the orphan evidence-table builders: nothing downstream `ref()`s
them, so SOURCE passthrough is the Snowflake serving copy.

Ownership and 13F holdings **do** have gold models, rewired onto silver
`ref()` (dbt-gold-silver-rewiring). SOURCE still holds the older Python
dimensional / passthrough mirrors.

---

## 1. Auditor report evidence (`AUDITED_BY`)

### DuckDB silver

DDL and merge live in `edgar_warehouse/silver_store.py`:
`sec_auditor_report_evidence` PK `(accession_number, evidence_fingerprint)`;
`merge_auditor_report_evidence`. Protected in
`edgar_warehouse/silver_protection.py`. Sharded reader allowlist:
`edgar_warehouse/silver_support/sharded_reader.py`.

Writer: `edgar_warehouse/application/auditor_evidence.py`
(`AuditorEvidenceRow`, PCAOB id + principal firm). Companion identity table
`sec_pcaob_firm_identity` is DuckDB + SILVER/LANDING only (0 rows live);
**not** in `SNOWFLAKE_EXPORT_TABLES`.

### Snowflake SOURCE

Created in `infra/snowflake/sql/bootstrap/01_source_stage.sql`
(`SEC_AUDITOR_REPORT_EVIDENCE`). Loaded by both:

- `infra/snowflake/sql/bootstrap/03_source_load_wrapper.sql` (`LOAD_EXPORTS_FOR_RUN`)
- `infra/snowflake/sql/bootstrap/06_fundamentals_load_wrapper.sql` (`LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN`, composite key `ACCESSION_NUMBER, EVIDENCE_FINGERPRINT`)

Registry: `edgar_warehouse/infrastructure/run_manifest_builder.py`
`SNOWFLAKE_EXPORT_TABLES["SEC_AUDITOR_REPORT_EVIDENCE"]`. Serving map:
`edgar_warehouse/serving/targets/snowflake.py` `GOLD_EXPORT_MAP`. Builder:
`_build_sec_auditor_report_evidence()` in
`edgar_warehouse/serving/source_dimensional_export.py` (SELECT from
`EDGARTOOLS_SILVER.SEC_AUDITOR_REPORT_EVIDENCE`).

**Live SOURCE count: 0.**

### Snowflake SILVER

Landing: `infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql` +
`13_silver_landing_ingest.sql` table list. dbt collapse:
`infra/snowflake/dbt/edgartools_gold/models/silver/sec_auditor_report_evidence.sql`
(`source('edgartools_silver_landing', 'SEC_AUDITOR_REPORT_EVIDENCE')`).
Declared in `models/sources.yml` under both `edgartools_source` and
`edgartools_silver_landing`.

**Live LANDING 0 / SILVER 0.**

### Snowflake GOLD

No `SEC_AUDITOR_REPORT_EVIDENCE` gold object (confirmed via
`INFORMATION_SCHEMA.TABLES`). Related gold table `ACCOUNTING_FLAGS`
(`models/gold/accounting_flags.sql`) carries `auditor_name` /
`auditor_pcaob_id` from silver `sec_accounting_flag` — **live 0 rows**, and
SOURCE `ACCOUNTING_FLAG` is also 0. That is the legacy `AUDITED_BY` fallback
in MDM, not the preferred evidence table.

### MDM / graph

`edgar_warehouse/mdm/pipeline.py` `_derive_audited_by` reads
`sec_auditor_report_evidence` first; if empty, `sec_accounting_flag`.
Graph view: `NEO4J_GRAPH_MIGRATION.GRAPH_EDGE_AUDITED_BY`
(`edgar_warehouse/mdm/snowflake_graph.py`).

**Live active-generation `AUDITED_BY` edges: 0.**

### Contract sketch

`infra/snowflake/sql/decision_contract/02_subject_bundle_read_issuer.sql`
`BUNDLE_AUDITOR` reads `EDGARTOOLS_SOURCE.SEC_AUDITOR_REPORT_EVIDENCE`
(layer is correct; CLAUDE.md’s older note that the sketch pointed at
`EDGARTOOLS_GOLD.SEC_AUDITOR_REPORT_EVIDENCE` is stale). Python semantics:
`edgar_warehouse/serving/subject_bundle_read.py` `_build_auditor_section`
prefers PCAOB id.

---

## 2. Employment events / `EMPLOYED_BY`

Two silver sources, not one.

### Item 5.02 events — `sec_employment_event`

- DuckDB: `silver_store.py` DDL + `merge_employment_events`.
- Writers: `warehouse_orchestrator.py` Item 5.02 parse
  (`Parse one Item 5.02 candidate 8-K into sec_employment_event`);
  `edgar_warehouse/application/workflows/fundamentals_ingest.py`
  (`db.merge_employment_events`).
- SOURCE / SILVER / landing / export: same passthrough pattern as auditor
  (`SEC_EMPLOYMENT_EVENT`, PK `ACCESSION_NUMBER, EVENT_INDEX`).
- **Live:** LANDING 11,221 (append-only, includes superseded parses);
  SILVER 7,676; SOURCE 7,676.

### DEF 14A proxy pay — `sec_executive_record`

- DuckDB: `silver_store.py` `sec_executive_record`.
- SOURCE dimensional: `EXECUTIVE_RECORD` (14,755).
- SILVER/LANDING: `SEC_EXECUTIVE_RECORD` (14,755).
- Gold: `EDGARTOOLS_GOLD.EXECUTIVE_RECORDS`
  (`models/gold/executive_records.sql`, `ref('sec_executive_record')`) —
  **14,755**. Bundle section uses these as `executive_pay`, not as the
  employment edge itself.

### MDM / graph

`_derive_employed_by` in `pipeline.py`:

1. `sec_executive_record` with `source_system="proxy_filing"`.
2. Then `sec_employment_event` with `source_system="item_502_filing"`.

Issuer bundle contract (`docs/subject-bundle-read.md`,
`subject_bundle_read.py` `EMPLOYMENT_SOURCE_SYSTEMS`) requires
`proxy_def14a` or `item_5_02`. **Those strings are not what derivation
writes.** A naive filter on the contract names would drop live edges.

Graph view `GRAPH_EDGE_EMPLOYED_BY`: **3 rows** on the active generation
despite thousands of silver events and 14,755 exec records. Evidence
tables exist; graph publication of this type is not caught up (and is
not a missing-table problem).

---

## 3. Subsidiary / parent evidence (`HAS_PARENT`)

### DuckDB silver

`sec_subsidiary_evidence` PK `(accession_number, document_name, row_ordinal)`;
`merge_subsidiary_evidence`. Parser:
`edgar_warehouse/application/subsidiary_exhibits.py` (Exhibit 21 / EX-8,
`parent_scope=registrant_disclosed`, `immediate_parent_known=false` unless
explicit). Contract:
`docs/release-readiness/parent-company-source-parser-contract.md`.

`TODOS.md` still records `parent_company_entity_id_always_none` as a
historical MDM gap; current `_derive_has_parent_company` reads
`sec_subsidiary_evidence` directly (not `MdmCompany.parent_company_entity_id`).
With 0 evidence rows, derivation still produces 0 edges.

### Snowflake

Same SOURCE passthrough + SILVER collapse as auditor.

**Live SOURCE/SILVER/LANDING: 0.** No gold table. Graph
`GRAPH_EDGE_HAS_PARENT_COMPANY`: **0**.

Python `_build_parent_section` fail-closes unless
`parent_inventory_complete=True`. Completeness of Exhibit 21 inventory is
not represented by a live table in this query.

`sec_thirteenf_filing` is unrelated; do not use SIC or 13F manager CIK as
parent evidence (already rejected in `TODOS.md`).

---

## 4. Institutional holdings (`holders_of_subject` / `subject_as_manager_portfolio`)

### Holdings rows

| Layer | Object | Live count |
| --- | --- | --- |
| DuckDB | `sec_thirteenf_holding` | schema+writer; not counted here |
| LANDING | `EDGARTOOLS_SILVER_LANDING.SEC_THIRTEENF_HOLDING` | 6,799,919 |
| SILVER | `EDGARTOOLS_SILVER.SEC_THIRTEENF_HOLDING` | 6,799,919 |
| SOURCE | `EDGARTOOLS_SOURCE.SEC_THIRTEENF_HOLDING` | 6,799,919 |
| GOLD | `EDGARTOOLS_GOLD.INSTITUTIONAL_HOLDINGS` | 6,799,919 |

Gold model: `models/gold/institutional_holdings.sql` — `ref('sec_thirteenf_holding')`,
adds `qoq_change_*`, `ownership_rank_within_period`, `is_current_holding`.

Parser: `edgar_warehouse/parsers/thirteenf.py`. Export:
`SNOWFLAKE_EXPORT_TABLES["SEC_THIRTEENF_HOLDING"]`;
`LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN`.

**Live gold columns** (`INFORMATION_SCHEMA.COLUMNS`): `CIK` (13F **manager**),
`ACCESSION_NUMBER`, `HOLDING_INDEX`, `PERIOD_OF_REPORT`, `CUSIP`,
`ISSUER_NAME` (text), `SECURITY_TITLE`, `SHARES_HELD`, `MARKET_VALUE`, …
There is **no `ISSUER_CIK`**, **no `MANAGER_CIK`**, **no `SHARES`**.

Sketch `BUNDLE_HOLDERS_OF_SUBJECT` selects `h.issuer_cik`, `h.manager_cik`,
`h.shares` from `EDGARTOOLS_GOLD.INSTITUTIONAL_HOLDINGS`. That view would
not compile against live gold. Repo-wide dbt has **zero** `issuer_cik`
columns.

Practical bind:

- `subject_as_manager_portfolio`: `INSTITUTIONAL_HOLDINGS.CIK = bundle_subject_cik`.
- `holders_of_subject`: match the issuer’s CUSIPs (MDM security / ticker /
  ownership titles) to `CUSIP` / `ISSUER_NAME`. There is no first-class
  issuer-CIK foreign key on 13F holdings.

### Filing header (restatement / effective status)

`sec_thirteenf_filing` is required by `_derive_institutional_holds`
(join + restatement `NOT EXISTS`). It exists in DuckDB, LANDING (14,364),
and SILVER (14,364).

**It is not in `SNOWFLAKE_EXPORT_TABLES`, not in SOURCE
`INFORMATION_SCHEMA.TABLES`, and has no gold model.** Agents that must
reproduce “effective public 13F set” without DuckDB should read
`EDGARTOOLS_SILVER.SEC_THIRTEENF_FILING`, not SOURCE.

### Graph

`GRAPH_EDGE_INSTITUTIONAL_HOLDS`: **0** on the active generation. Silver/gold
holdings are populated; MDM/graph `INSTITUTIONAL_HOLDS` is not. Known
long-running derivation/cursor issue (`CLAUDE.md` INSTITUTIONAL_HOLDS
entries); this inventory does not re-open that fix.

---

## 5. Ownership rows used with `IS_INSIDER`

### Raw Form 3/4/5 tables (person + transactions)

DuckDB / SILVER landing / SILVER collapse (dbt `models/silver/sec_ownership_*.sql`):

| Table | LANDING | SILVER |
| --- | --- | --- |
| `sec_ownership_reporting_owner` | 61,752 | 59,030 |
| `sec_ownership_non_derivative_txn` | 108,163 | 78,469 |
| `sec_ownership_derivative_txn` | 4,708 | 2,969 |

Silver `sec_ownership_reporting_owner` **joins in issuer `cik`** from
`sec_company_filing` (Ticket 06 comment in the dbt model). DuckDB’s own
table does not have that column (`silver_parity.py` exclude list).

**None of these three raw tables exist in `EDGARTOOLS_SOURCE`.** They are
not in `SNOWFLAKE_EXPORT_TABLES`. MDM `_derive_is_insider` reads silver:

```sql
FROM sec_ownership_reporting_owner o
JOIN sec_company_filing f ON o.accession_number = f.accession_number
```

(`pipeline.py`). Parser: `edgar_warehouse/parsers/ownership.py`.

### Dimensional / gold ownership (accession for agent-grade join)

| Object | Live count |
| --- | --- |
| SOURCE `OWNERSHIP_HOLDINGS` | 51,046 |
| SOURCE `OWNERSHIP_ACTIVITY` | 81,455 |
| GOLD `OWNERSHIP_HOLDINGS` | 42,507 |
| GOLD `OWNERSHIP_ACTIVITY` | 81,438 |

Gold models: `models/gold/ownership_holdings.sql`,
`ownership_activity.sql` — `ref()` silver txns + `sec_company_filing` +
`sec_ownership_reporting_owner`.

**Live GOLD `OWNERSHIP_HOLDINGS` columns:** `FACT_KEY`, `COMPANY_KEY`,
`DATE_KEY`, `PARTY_KEY`, `SECURITY_KEY`, `ACCESSION_NUMBER`, `OWNER_INDEX`,
`SHARES_OWNED_AFTER`, `OWNERSHIP_DIRECT_INDIRECT`. No `OWNER_CIK`, no
`OWNER_NAME`. Activity similarly keeps accession + txn measures, not
person identity.

`build_issuer_subject_bundle` joins graph edges to gold rows via
`_person_key` (`person_entity_id` / `owner_name`). Gold holdings as
currently published cannot supply the name side; they *can* supply
`accession_number` if the caller already has a person key from the graph.
Graph edges also carry `SOURCE_ACCESSION`.

### Graph

`GRAPH_EDGE_IS_INSIDER`: **1,617** on the active generation
(`GRAPH_ACTIVE_POINTER.POINTER_ID = 'active'`, `ACTIVATED_AT = 2026-08-22`).
This is the only neighborhood relationship type with material graph
coverage besides `HOLDS` / `COMPANY_HOLDS` / `ISSUED_BY` (out of this
ticket’s minimum set except as gold ownership context).

---

## Export / manifest registry (predecessor ticket 08)

`edgar_warehouse/infrastructure/run_manifest_builder.py` `SNOWFLAKE_EXPORT_TABLES`
includes, for this neighborhood:

- `SEC_SUBSIDIARY_EVIDENCE`, `SEC_AUDITOR_REPORT_EVIDENCE`, `SEC_EMPLOYMENT_EVENT`
- `SEC_THIRTEENF_HOLDING`
- `OWNERSHIP_ACTIVITY`, `OWNERSHIP_HOLDINGS`
- `EXECUTIVE_RECORD`, `ACCOUNTING_FLAG`

Tests: `tests/unit/test_agent_evidence_source_export.py` (registry membership
+ builder round-trip against a fake SILVER connection).

**Not on the SOURCE export path, but required for some neighborhood
semantics:**

- `sec_thirteenf_filing` (effective 13F set)
- `sec_ownership_reporting_owner` / `*_txn` (person identity, director/officer flags)
- `sec_pcaob_firm_identity`
- `sec_company_filing` (issuer CIK for an ownership accession; SILVER has it)

Agents can still avoid DuckDB for those by reading `EDGARTOOLS_SILVER`
(landing collapse). They cannot get them from SOURCE or from gold except
where gold already folded the join (issuer `cik` on silver owners; **not**
copied through to gold ownership).

---

## Decision Contract objects

- Schema `EDGARTOOLS_DECISION` exists in prod; `INFORMATION_SCHEMA.TABLES`
  returns **no objects**. Sketches in
  `infra/snowflake/sql/decision_contract/02_subject_bundle_read_issuer.sql`
  are documentation, not live views.
- Python contract semantics:
  `edgar_warehouse/serving/subject_bundle_read.py` (unit-tested; does not
  query Snowflake itself — callers pass pre-filtered rows).
- Graph pointer: `NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER` has one
  `active` row with a non-null generation (activated 2026-08-22). Neighborhood
  graph views filter to that generation.

---

## Implications for ticket 05 (v1 agent-grade sections)

Not decided here; recorded so ticket 05 does not assume empty-vs-missing
wrongly:

1. **Auditor / parent:** objects exist on SOURCE+SILVER, **empty**. v1
   cannot be `present`. `unavailable` vs `empty` depends on whether
   “parser never loaded Exhibit 21 / auditor evidence for the universe”
   counts as missing inventory (`unavailable`) or complete-and-zero
   (`empty`). Live 0 across landing/silver/source is the stronger
   “never populated” signal, not a collapse bug.
2. **Employment:** silver evidence is real; graph has 3 edges; contract
   `source_system` vocabulary mismatches pipeline. Gold exec pay is
   usable as the pay sidecar.
3. **Holders of subject:** gold 13F is real at 6.8M rows but the sketch’s
   column names are wrong, and `issuer_cik` does not exist anywhere in
   dbt. Graph `INSTITUTIONAL_HOLDS` cannot back the section (0 edges).
4. **Insiders:** graph + silver owners + gold accession are all populated.
   Gold-only ownership is not sufficient for person identity.
5. **Do not send agents to DuckDB** for these facts: SILVER (and SOURCE
   passthrough where non-empty) already hold the Snowflake copy. DuckDB
   remains the ingest merge surface (`silver_store.py`) feeding landing.

---

## Sources cited

| Kind | Path |
| --- | --- |
| DuckDB DDL/writers | `edgar_warehouse/silver_store.py` |
| Parsers | `application/auditor_evidence.py`, `application/subsidiary_exhibits.py`, `parsers/ownership.py`, `parsers/thirteenf.py`, `application/warehouse_orchestrator.py` (Item 5.02), `application/workflows/fundamentals_ingest.py` |
| Export registry | `edgar_warehouse/infrastructure/run_manifest_builder.py`, `serving/targets/snowflake.py`, `serving/source_dimensional_export.py` |
| SOURCE DDL/load | `infra/snowflake/sql/bootstrap/01_source_stage.sql`, `03_source_load_wrapper.sql`, `06_fundamentals_load_wrapper.sql` |
| SILVER landing | `infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql`, `13_silver_landing_ingest.sql` |
| dbt silver | `infra/snowflake/dbt/edgartools_gold/models/silver/sec_{auditor_report_evidence,employment_event,subsidiary_evidence,thirteenf_*,ownership_*}.sql` |
| dbt gold | `models/gold/{institutional_holdings,ownership_holdings,ownership_activity,executive_records,accounting_flags}.sql`, `models/sources.yml`, `models/gold/gold.yml` |
| MDM derive | `edgar_warehouse/mdm/pipeline.py` (`_derive_is_insider`, `_derive_employed_by`, `_derive_has_parent_company`, `_derive_audited_by`, `_derive_institutional_holds`) |
| Graph | `edgar_warehouse/mdm/snowflake_graph.py` (`GRAPH_EDGE_*` views) |
| Contract | `docs/subject-bundle-read.md`, `edgar_warehouse/serving/subject_bundle_read.py`, `infra/snowflake/sql/decision_contract/02_subject_bundle_read_issuer.sql` |
| Tests | `tests/unit/test_agent_evidence_source_export.py` |
| Live | `edgartools-prod` / `EDGARTOOLS_PROD`, 2026-09-10 |
