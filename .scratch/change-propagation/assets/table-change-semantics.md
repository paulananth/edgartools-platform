# Silver table change and dependency semantics

Inventory date: 2026-08-20

Repository baseline: `1f411244` plus the planning-only change-propagation commits

Scope: the 31 current `EDGARTOOLS_SILVER_LANDING` tables

## Purpose and method

This is a factual inventory of current behavior. It does not select the target
change-propagation design. The matrix was produced by:

1. executing the runtime DuckDB DDL in memory and reflecting every landing
   table, column, and primary key;
2. reading each current writer's conflict and replacement behavior;
3. comparing the append-only Snowflake landing generator and loader with the
   generated dbt silver collapse models;
4. resolving the committed dbt `ref()` graph to gold descendants; and
5. reading the MDM resolver, relationship derivation, coverage, graph export,
   and parity consumers.

The landing scope is the protected canonical registry, excluding the
operational lease table, plus the guidance-reject log. Although generator
comments still contain an older “30 tables” count, the generated schema,
declared dbt sources, and reflected runtime DDL currently contain 31 tables.

## Cross-table findings

### Physical write path

- DuckDB is current-state and keyed for 30 tables. Writers use `ON CONFLICT`
  upserts; the guidance-reject table is the one keyless append-only log.
- Snowflake landing is append-only. Every successful decorated DuckDB write
  records the caller's input rows and later emits one Parquet object per
  non-empty table.
- Empty output is omitted entirely. There is no zero-row file, table outcome,
  replacement-scope completion record, or tombstone.
- The current object identity is table, business date, and run ID. It does not
  include producer, logical batch, attempt, source revision, or content hash.
  Concurrent windows sharing a run ID can overwrite the same object and
  manifest paths.
- Snowflake loads by table prefix with `COPY INTO`; the run manifest is not the
  authoritative exact-file input to the loader. Native copy history therefore
  participates in retry behavior.
- Generated dbt silver models collapse landing rows by business key and newest
  `parse_sequence`. The reject log is a passthrough view. Three tables preserve
  selected first-seen columns, and accounting flags preserve only three
  last-non-null score fields.

### Field classification

The matrix uses these classifications:

- **Domain**: source business values, source evidence, and stable provenance
  that can affect current or historical meaning.
- **Interpretation**: `parser_version`. It changes how source material was
  interpreted, but is not currently part of a uniform source-revision identity.
- **Operational**: `first_sync_run_id`, `last_sync_run_id`, `last_synced_at`,
  `ingested_at`, and landing-only `parse_sequence`.
- **Asynchronous enrichment**: `mdm_entity_id`. It is written after parsing and
  currently shares the source table row rather than a separate overlay.

Every domain/evidence column not explicitly listed as interpretation,
operational, or asynchronous enrichment remains domain content. No landing row
has a uniform contract version, source schema version, parser configuration
version, logical source revision, lifecycle operation, or source-change ID.

### Common deletion, no-op, and retry capability

Unless a row below states a stronger table-specific behavior:

- **Deletion:** DuckDB has no retirement interval and landing has no tombstone.
  Missing rows cannot remove an existing Snowflake/dbt silver row.
- **No-op:** there is no silver domain-content hash. Re-emitting identical
  business content creates another landing row and a newer parse sequence.
- **Retry:** keyed DuckDB upserts usually converge in current state, but landing
  has no row-level event identity. A retry can overwrite an object before load,
  be skipped by copy history, or load another parse event. Last-write ordering
  is arrival/parse sequence, not logical source revision.

## Table matrix

In the dbt column, `silver: same-name` means the generated model has the same
lowercase name as the table and produces one current row per reflected business
key. Gold names are transitive descendants from the committed dbt graph.

### Company, submissions, feed, and raw evidence

| Table and business key | Current writer and change behavior | Source/version and field classification | MDM consumer and required neighbors | dbt silver and gold descendants | Graph eligibility impact | Table-specific lifecycle gaps |
| --- | --- | --- | --- | --- | --- | --- |
| `sec_company` — `cik` | Upsert; all source-owned descriptive fields are last-write-wins. `first_sync_run_id` is first-insert-wins. | Domain: company identity/classification fields. Operational: first/last run and sync time. Async: `mdm_entity_id`. No parser/source hash. Source is the submissions company snapshot. | Company resolver; joins ticker rows and optional tracking state. The company CIK is also the issuer/registrant neighbor for ownership, filing, financial, subsidiary, auditor, employment, and 13F work. | silver: same-name; gold: `company`. | Company node; a changed canonical company can affect every incident relationship and node properties. | Snapshot disappearance cannot retire a company. Full-row MDM backfill can race later parser rows because enrichment shares this row shape. |
| `sec_company_address` — `(cik, address_type)` | Upsert by address type; no replacement delete when an address type disappears. | Domain: address fields. Operational: last run/time. No parser/source hash. Source is the submissions snapshot. | No current resolver or relationship consumer beyond parity; company CIK is the natural future neighbor. | silver: same-name; no gold descendant. | No current direct graph projection. | Stale address types persist; empty address sets are unrepresentable. |
| `sec_company_former_name` — `(cik, ordinal)` | The submissions composite operation deletes all DuckDB rows for the CIK, then inserts/upserts the replacement list. | Domain: former name and change date. Operational: last run. No parser/source hash. | No current MDM consumer beyond parity. | silver: same-name; no gold descendant. | No current direct graph projection. | The DuckDB replacement delete is invisible to landing; removed ordinals remain current in dbt silver. An empty replacement emits nothing. |
| `sec_company_submission_file` — `(cik, file_name)` | The submissions composite operation deletes all DuckDB rows for the CIK, then inserts/upserts the replacement manifest. | Domain: file name, filing count, date span. Operational: last run/time. No parser/source hash. | No current MDM consumer beyond parity. | silver: same-name; no gold descendant. | No current direct graph projection. | The DuckDB replacement delete is invisible to landing; removed files and a complete empty manifest cannot propagate. |
| `sec_company_ticker` — `(cik, ticker, source_name)` | Replaces the whole DuckDB scope for one `source_name` by delete then insert. Rows are ranked by source order. | Domain: CIK, ticker, exchange, source name/rank. Operational: last run/time. No parser/source hash. Source is a reference catalog snapshot. | Company resolver and company pipeline enrichment; neighbor is the company CIK. | silver: same-name; gold: `ticker_reference`. | Can change company node identifiers/properties and company resolution. | Deleted catalog members are invisible to landing; an empty catalog writes no rows. Current key includes CIK, so reassignment of a ticker can leave the old CIK/ticker row current. |
| `sec_company_filing` — `accession_number` | Two-pass bulk upsert. First seen preserves `cik`, `act`, `file_number`, `film_number`, and `items`; latest updates filing metadata. Submission refresh adds filings but does not retire absent accessions. | Domain: accession, issuer, form, dates, SEC identifiers, document metadata. Operational: last run/time. No parser/source hash. Accession is the implicit source identity. | Required issuer-CIK join for ownership person/security resolution and `IS_INSIDER`, `HOLDS`, `COMPANY_HOLDS`, and `ISSUED_BY`. Also joins ADV gold models where CIK is needed. | silver: same-name with first/last split; gold: `filing_activity`, `filing_detail`, `ownership_activity`, `ownership_holdings`, `adviser_disclosures`, `adviser_offices`, `private_funds`. | Indirectly affects company/person/security nodes and ownership edges through accession-to-issuer resolution. | No document-set completeness or accession retirement operation. Same accession with conflicting immutable fields is silently first-seen rather than an explicit conflict disposition. |
| `sec_current_filing_feed` — `accession_number` | Upsert of the most recent feed representation. | Domain: filing/feed URLs, summary, publication time, raw-object reference. Operational: last run/time. No parser version. Source URL/raw object provide provenance. | No current MDM consumer beyond parity. | silver: same-name; no gold descendant. | No current graph projection. | No active production producer was found for the declared landing contract; feed disappearance and corrections have no explicit lifecycle identity. |
| `sec_raw_object` — `raw_object_id` | Upsert by raw-object ID. `fetched_at` is first-seen; source context, storage/content metadata, SHA-256, HTTP status, and source validators update. | Domain/evidence: source type/key context, storage path, byte size, SHA-256, HTTP/source validators. Acquisition metadata: first-fetch time and current status. No parser version. SHA-256 is the strongest current byte identity. | No current MDM consumer beyond parity. | silver: same-name; no gold descendant. | No current graph projection. | Physical object evidence is retained, but a reused raw-object ID can update its content hash while preserving only the first fetch time, and no link uniformly binds a raw object/version to every parsed table row or its consumption outcome. |
| `sec_filing_attachment` — `(accession_number, document_name)` | Upsert attachment metadata by filing/document. | Domain/evidence: sequence, type, description, URL, primary flag, raw-object ID. Operational: last run. No parser version. | No current resolution consumer; coverage code only inspects availability. | silver: same-name; no gold descendant. | No current graph projection. | A changed filing document set cannot retire a removed attachment or prove completeness. |
| `sec_filing_text` — `(accession_number, text_version)` | Upsert extracted-text locator and digest for a version. | Domain/evidence: source document, storage path, text SHA-256, character count, extraction time. `text_version` is table-specific versioning, not the shared contract version. | No current MDM consumer beyond parity. | silver: same-name; no gold descendant. | No current graph projection. | New versions accumulate, but there is no declared current-version policy, retirement, or run-bound link to downstream text products. |

### Ownership

| Table and business key | Current writer and change behavior | Source/version and field classification | MDM consumer and required neighbors | dbt silver and gold descendants | Graph eligibility impact | Table-specific lifecycle gaps |
| --- | --- | --- | --- | --- | --- | --- |
| `sec_ownership_reporting_owner` — `(accession_number, owner_index)` | Upsert complete owner row by filing position. | Domain: owner identity and roles. Interpretation: `parser_version`. Operational: last run. Async: `mdm_entity_id`. Accession/index are implicit source identity. | Person resolution and `IS_INSIDER`; requires `sec_company_filing` for issuer CIK and may compare owner CIK with `sec_company`. Neighbor keys are owner CIK/name, accession, and issuer CIK. | silver: same-name plus issuer `cik` enrichment; gold: `ownership_activity`, `ownership_holdings`. | Person/company nodes and `IS_INSIDER`; also supplies owner endpoint for holdings edges. | A corrected filing with fewer owners cannot retire removed indexes. Role-only changes do not have an explicit relationship mutation/outbox identity. |
| `sec_ownership_non_derivative_txn` — `(accession_number, owner_index, txn_index)` | Upsert complete transaction row by filing positions. | Domain: security, transaction, holdings, ownership fields. Interpretation: parser version. Operational: last run. Async: `mdm_entity_id`. | Security resolution and `HOLDS`, `COMPANY_HOLDS`, `ISSUED_BY`; requires reporting owner at the same owner index and company filing for issuer CIK. | silver: same-name plus issuer `cik` enrichment; gold: `ownership_activity`, `ownership_holdings`. | Security/person/company nodes and holdings/issuer edges. | Removed transactions cannot retire. The positional key can reinterpret a corrected reordered filing without a stable transaction-content identity. |
| `sec_ownership_derivative_txn` — `(accession_number, owner_index, txn_index)` | Upsert complete derivative transaction row by filing positions. | Domain: derivative security, underlying security, transaction, exercise/expiry, holdings fields. Interpretation: parser version. Operational: last run. Async: `mdm_entity_id`. | Same security and relationship paths as non-derivative transactions; requires owner and issuer neighbors. | silver: same-name plus issuer `cik` enrichment; gold: `ownership_activity`, `ownership_holdings`. | Security/person/company nodes plus `HOLDS`, `COMPANY_HOLDS`, and `ISSUED_BY`. | Removed or reordered transactions cannot be retired or distinguished by source revision. |

### ADV

| Table and business key | Current writer and change behavior | Source/version and field classification | MDM consumer and required neighbors | dbt silver and gold descendants | Graph eligibility impact | Table-specific lifecycle gaps |
| --- | --- | --- | --- | --- | --- | --- |
| `sec_adv_filing` — `accession_number` | Bulk upsert; all non-key fields are latest-write-wins. `filing_action`/status are stored as values, not generic lifecycle operations. | Domain: adviser identifiers, effective/status/action data. Interpretation: parser version. Operational: last run. Async: `mdm_entity_id`. Accession and optional source format identify the filing; no source hash. | Adviser resolution with headquarters from `sec_adv_office`; adviser endpoint for `MANAGES_FUND`. Neighbor keys are accession and CRD number. | silver: same-name; gold: `adviser_disclosures`, `adviser_offices`, `private_funds`. | Adviser node and `MANAGES_FUND`; adviser property changes can rebuild incident graph content. | Rolling-window disappearance is not retirement. Filing actions are domain-specific and do not close arbitrary prior rows. |
| `sec_adv_office` — `(accession_number, office_index)` | Upsert office by filing position. | Domain: office and headquarters fields. Interpretation: parser version. Operational: last run. | Adviser resolver/bulk path; requires filing accession/CRD to identify adviser. | silver: same-name; gold: `adviser_offices`. | Adviser node properties through canonical adviser resolution; no direct edge. | Removed/reordered offices cannot retire; complete office scope is not represented. |
| `sec_adv_disclosure_event` — `(accession_number, event_index)` | Upsert disclosure event by filing position. | Domain: category, date, reported flag, description. Interpretation: parser version. Operational: last run. | No current MDM consumer beyond parity. | silver: same-name; gold: `adviser_disclosures`. | No current graph projection. | Removed/reordered events cannot retire; no disclosure-scope completeness. |
| `sec_adv_private_fund` — `(accession_number, fund_index)` | Bulk upsert; all non-key fields are latest-write-wins. | Domain: adviser/fund identifiers, role/action, name/type/jurisdiction/AUM/effective date. Evidence: dataset period and source SHA-256. Interpretation: parser version. Operational: last run. Async: `mdm_entity_id`. | Fund resolution and `MANAGES_FUND`; requires adviser identity via CRD/accession and may reconsider both endpoints. | silver: same-name; gold: `private_funds`, `adv_fund_count_reconciliation`. | Fund/adviser nodes and `MANAGES_FUND`. | Removed/reordered fund entries cannot retire. `filing_action` does not provide generic scope completion. |
| `sec_adv_firm_roster` — `(adviser_crd_number, dataset_period)` | Upsert aggregate roster row for a firm and monthly dataset. | Domain: private-fund counts/flags/assets. Evidence: dataset period and source SHA-256. Interpretation: parser version. Operational: last run. | No current MDM consumer beyond parity. | silver: same-name; gold: `adv_fund_count_reconciliation`. | No current graph projection. | Snapshots accumulate by period, but there is no declared current period/scope completion or member retirement. |

### Financial, earnings, guidance, and executives

| Table and business key | Current writer and change behavior | Source/version and field classification | MDM consumer and required neighbors | dbt silver and gold descendants | Graph eligibility impact | Table-specific lifecycle gaps |
| --- | --- | --- | --- | --- | --- | --- |
| `sec_financial_fact` — `(cik, accession_number, concept, fiscal_period, segment, period_end, period_start)` | Two-pass bulk upsert. `fiscal_year`, `form_type`, and `unit` are first-seen; value, decimals, and parser version update. | Domain: XBRL context, concept, value/unit/decimals/segment. Interpretation: parser version. Operational: ingestion time. Accession is implicit source identity; no source hash. | No active resolver; security resolution from XBRL is explicitly deferred. Coverage only reports it. | silver: same-name with first/last split; gold: `financial_facts`. | No current direct graph projection. | Removed facts cannot retire. Same key with conflicting first-seen unit/form/year is silently preserved rather than quarantined. |
| `sec_financial_derived` — `(cik, accession_number, fiscal_period, period_end)` | Two-pass bulk upsert. Fiscal year/form are first-seen; all metrics and parser version update. | Domain: financial metrics and ratios. Interpretation: parser version. Operational: ingestion time. Accession is implicit source identity. | No current MDM consumer beyond parity. | silver: same-name with first/last split; gold: `financial_derived`, then `financial_factors`. | No current graph projection. | Removed or no-longer-derivable metrics cannot retire; a corrected parser can leave old rows with no explicit supersession. |
| `sec_earnings_release` — `(cik, accession_number)` | Upsert derived earnings summary. `filing_date` is first-seen; period, values, flags, and parser version update. | Domain: filing/period, GAAP values, non-GAAP/guidance flags. Interpretation: parser version. Operational: ingestion time. | No current MDM consumer beyond parity. | silver: same-name; gold: `earnings_releases`. | No current graph projection. | A parser that stops recognizing an earnings release cannot retire the prior row. |
| `sec_guidance_fact` — `(cik, metric, fiscal_year, fiscal_quarter, as_of, accession_number, is_non_gaap, source_system)` | Upsert the keyed guidance assertion; latest row replaces values, excerpt, confidence, and parser version. | Domain: `fact_key`, company/ticker, period, values/unit/currency, source reference/excerpt/confidence. Interpretation: parser version. Operational: ingestion time. | No current MDM consumer beyond parity. | silver: same-name; gold: `guidance_facts`. | No current graph projection. | No retirement when a reparsed document no longer supports a fact; `fact_key` is not the declared primary key. |
| `sec_guidance_fact_reject` — no key | Append every rejected candidate. | Domain/audit: CIK, accession, metric, reason, raw payload. Interpretation: parser version. Operational: ingestion time. | No current MDM consumer beyond parity. | silver: same-name passthrough view; no gold descendant. | No current graph projection. | Duplicate retry appends duplicate rejects; no reject fingerprint or supersession identity. |
| `sec_accounting_flag` — `(cik, accession_number)` | Upsert accounting/auditor facts. `fiscal_year`, `period_end`, and `form_type` are first-seen. Auditor/ICFR fields update; three forensic scores are last-non-null. A separate thin score backfill emits only key plus scores. | Domain: period/form, auditor, ICFR, change flag, forensic scores. Interpretation: parser version. Operational: ingestion time. | Legacy `AUDITED_BY` input and audit-firm creation when stronger auditor evidence is absent; neighbor is company CIK and auditor identity/PCAOB ID. | silver: same-name with last-non-null scores; gold: `accounting_flags`. | Company/audit-firm nodes and `AUDITED_BY`. | Thin backfill can make all non-score fields null in generated silver because only the three scores use last-non-null windows. Conflicting first-seen fiscal metadata is not surfaced, and there is no auditor retirement. |
| `sec_executive_record` — `(cik, accession_number, exec_name)` | Upsert proxy executive/compensation record. `fiscal_year` is first-seen; role, compensation, and parser version update. | Domain: executive name/role and compensation fields. Interpretation: parser version. Operational: ingestion time. | Person resolution and `EMPLOYED_BY`; neighbor is company CIK. | silver: same-name; gold: `executive_records`. | Person/company nodes and `EMPLOYED_BY`. | Removed executives cannot retire; name in the key makes a corrected name appear as an additional person. |
| `sec_employment_event` — `(accession_number, event_index)` | Upsert event by filing position. Company `cik` is first-seen; event/person/role/compensation/effective-date fields and parser version update. | Domain: company, event type, person/roles, compensation, effective date. Interpretation: parser version. Operational: ingestion time. | Person resolution and temporal `EMPLOYED_BY`; neighbor is company CIK and potentially prior employment relation. | silver: same-name; no gold descendant. | Person/company nodes and temporal `EMPLOYED_BY`. | Removed/reordered events cannot retire; event index is positional rather than a content fingerprint, and a conflicting first-seen CIK is not surfaced. |

### Auditor, subsidiary, and institutional evidence

| Table and business key | Current writer and change behavior | Source/version and field classification | MDM consumer and required neighbors | dbt silver and gold descendants | Graph eligibility impact | Table-specific lifecycle gaps |
| --- | --- | --- | --- | --- | --- | --- |
| `sec_auditor_report_evidence` — `(accession_number, evidence_fingerprint)` | Upsert only amendment-link fields and last run; the core evidence is effectively first-seen for a fingerprint. | Domain/evidence: registrant, filing/document/period/report, firm identity/location/PCAOB ID, locator, source SHA-256, fingerprint, amendment chain. Interpretation: parser version. Operational: last run. | Primary `AUDITED_BY` input; creates/resolves audit-firm endpoint and joins company by registrant CIK. | silver: same-name; no gold descendant. | Company/audit-firm nodes and `AUDITED_BY`, including evidence properties. | Evidence absent from a corrected document cannot retire; amendment resolution is not a generic scope completion. |
| `sec_pcaob_firm_identity` — `(pcaob_firm_id, snapshot_sha256)` | Upsert one firm identity per source snapshot hash. Snapshot URI is first-seen; name/location/status and last run update within the same snapshot key. | Domain: PCAOB identity, canonical name/location/status. Evidence: snapshot URI/SHA-256. Operational: last run. No parser version. | No current MDM pipeline consumer beyond parity; current audit-firm creation comes from auditor/accounting evidence. | silver: same-name; no gold descendant. | No current direct graph projection. | Multiple snapshots accumulate with no explicit current snapshot or retirement of firms missing from a later complete catalog. |
| `sec_subsidiary_evidence` — `(accession_number, document_name, row_ordinal)` | Upsert extracted subsidiary row by document position. Registrant CIK and document type are first-seen; legal name/jurisdiction, parent/effective/evidence fields, parser version, and last run update. | Domain/evidence: registrant, document, legal name/jurisdiction, parent scope, effective date, locator, source SHA-256. Interpretation: parser version. Operational: last run. | Creates/resolves subsidiary company candidates and derives `HAS_PARENT_COMPANY`; neighbor is registrant company CIK and subsidiary identity. | silver: same-name; no gold descendant. | Company nodes and `HAS_PARENT_COMPANY`. | Removed/reordered exhibit rows cannot retire; positional key can retain an obsolete legal name as another company, and conflicting first-seen document identity is not surfaced. |
| `sec_thirteenf_filing` — `accession_number` | Upsert filing amendment/effective state. CIK, reporting period, filing date, and form are first-seen; amendment, omission, `effective_status`, `superseded_by_accession`, and parser version update. | Domain: filer, reporting period/date/form, amendment, omission, effective/supersession. Interpretation: parser version. Operational: ingestion time. | Required neighbor for `INSTITUTIONAL_HOLDS`. Current MDM joins by accession and excludes a filing only when a later filing for the adviser/period has `amendment_type = 'restatement'`; it does not read `effective_status` or `superseded_by_accession`. | silver: same-name; no direct gold descendant. | Accession, adviser/period, amendment type, filing date, and later-restatement presence affect `INSTITUTIONAL_HOLDS`; stored effective/supersession fields currently do not. Endpoints are adviser and security. | The row stores the strongest retirement-like fields in current silver, but current graph eligibility does not consume them. Holdings have no tombstones or scope-complete membership digest, and conflicting first-seen filing identity is not surfaced. |
| `sec_thirteenf_holding` — `(cik, accession_number, holding_index)` | Upsert only shares held, market value, security class, and parser version. Reporting period, CUSIP, issuer/title, put/call, discretion, and all voting fields are first-seen. | Domain: filer, filing/report period, CUSIP, issuer/security, position/value/class/voting. Interpretation: parser version. Operational: ingestion time. | Derives `INSTITUTIONAL_HOLDS`; requires the filing's current restatement-selection context, an adviser endpoint for the filing manager CIK, and a security identity by CUSIP/title. | silver: same-name; gold: `institutional_holdings`. | Adviser/security nodes and `INSTITUTIONAL_HOLDS`. | Removed/reordered holdings cannot retire directly. Correctness depends on a later-restatement query rather than an explicit holding-scope replacement, and conflicts in first-seen security/voting identity are not surfaced. |

## Dependency closure summary

The current code implies these minimum neighbor groups. They are not encoded in
one runtime dependency registry today:

| Changed input group | Current correctness-required MDM/graph neighbors |
| --- | --- |
| Company or ticker | Company CIK, canonical company entity, company graph node, and every incident relationship whose properties or eligibility use the company. |
| Ownership reporting owner | Filing accession to issuer CIK, owner person/company identity, all transactions at the owner index, `IS_INSIDER`, and incident holding relationships. |
| Ownership transaction | Filing issuer CIK, reporting owner at owner index, security identity, and `HOLDS`/`COMPANY_HOLDS`/`ISSUED_BY`. |
| ADV filing or office | Adviser CRD/accession, headquarters office set, adviser entity/node, and incident managed funds. |
| ADV private fund | Adviser endpoint, fund identity/node, and `MANAGES_FUND`. |
| Subsidiary evidence | Registrant company, subsidiary company candidate, and `HAS_PARENT_COMPANY`. |
| Executive or employment evidence | Company, person candidate, existing temporal employment interval, and `EMPLOYED_BY`. |
| Auditor evidence or accounting flag | Registrant company, audit-firm identity/PCAOB ID, competing evidence for the same report period, and `AUDITED_BY`. |
| 13F filing or holding | Filer/period filing set, later-restatement selection, filer adviser identity, security identity, and `INSTITUTIONAL_HOLDS`; stored effective/supersession fields are not current MDM eligibility inputs. |

## Current representational capability

| Capability | Current state |
| --- | --- |
| New keyed row | Representable in DuckDB and landing for all keyed tables. |
| Modified keyed row | Representable as an upsert/latest parse, but ordered by parse arrival rather than logical source revision. |
| Immutable observation | Partially representable where the business key includes a stable accession, digest, or version; still lacks a uniform event identity. |
| Retirement | Only table-specific status/supersession fields can imply it. There is no shared `RETIRE` operation or validity interval. |
| Scoped replacement | DuckDB performs it for ticker catalogs, former names, and submission files; landing/dbt cannot reproduce the deletes. |
| Complete empty scope | Not representable because empty buffers and tables are omitted. |
| Semantic no-op | Not detected in silver; identical content is re-emitted. |
| Parser/configuration reprocess | Parser version exists on many derived tables, but there is no uniform configuration/schema identity or child-run reason. |
| Deterministic retry | DuckDB keyed upserts are mostly idempotent; landing paths, copy history, and parse-sequence ordering are not a durable retry contract. |
| Out-of-order protection | None at the shared silver boundary; later arrival wins even when its logical source revision is older. |
| Quarantine | Guidance rejects are append-only and MDM has quarantine state, but silver changes lack a shared poisoned-change disposition. |
| Downstream publication barrier | Per-table generated models and native histories exist; there is no run-bound expected-producer barrier or aligned composite watermark. |

## Evidence pointers

- Runtime schema and writers: `edgar_warehouse/silver_store.py`
- Landing capture behavior: `edgar_warehouse/serving/silver_landing_export.py`
- Landing object and manifest behavior: `edgar_warehouse/serving/silver_landing_writer.py`
- Landing schema scope: `infra/scripts/generate_silver_landing_ddl.py`
- dbt silver collapse exceptions and authority rules:
  `infra/scripts/generate_silver_dbt_models.py`
- Snowflake prefix loader: `infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql`
- dbt sources and model DAG: `infra/snowflake/dbt/edgartools_gold/models/`
- MDM entities and relationships: `edgar_warehouse/mdm/pipeline.py`,
  `edgar_warehouse/mdm/adv_bulk.py`, and `edgar_warehouse/mdm/resolvers/`
- MDM parity-only table coverage: `edgar_warehouse/mdm/silver_parity.py`
- Graph eligibility and serving projection: `edgar_warehouse/mdm/snowflake_graph.py`
