# Spec: Firm Roster CSV completeness cross-check

**Status:** ready-for-agent
**Type:** spec
**Date:** 2026-07-28
**Repo:** edgartools-platform
**Related:** [ADV Pipeline map](../adv-pipeline/map.md) · [08 — Design the Firm Roster CSV Completeness Cross-Check](../adv-pipeline/issues/08-firm-roster-crosscheck-design.md) · [ADR 0002 — Silver SoE; edgartools-exclusive SEC I/O; optional bronze](../../docs/adr/0002-silver-soe-edgartools-exclusive.md)

## Problem Statement

The platform's per-fund adviser data comes entirely from SEC/IAPD's `advFilingData`
monthly feed, which is a rolling delta of filing *activity* (~17% of firms per month),
not a full-universe snapshot (ADV Pipeline map, ticket 01's finding). There is currently
no independent signal that would catch a firm whose fund count silently drifted from
reality — a parsing bug, a missed filing, or a gap in the rolling window would produce no
visible error; the platform would just quietly under- or over-count that firm's private
funds with nothing to flag it. SEC separately publishes a true full-universe snapshot (the
Firm Roster CSV) every month, but it only carries aggregate private-fund *counts* per
firm, not per-fund identity — useful as a completeness check, not as a replacement data
source.

## Solution

Ingest the Firm Roster CSV as a narrow, independent data source (CRD + aggregate
private-fund count columns only) and reconcile it against the `advFilingData`-derived
per-fund data already in silver, via a new dbt gold-layer view that flags firms where the
two disagree. This is purely additive visibility — per the ADV Pipeline map's standing
requirement (ticket 02's Notes), it must never gate MDM entity resolution or graph sync.
The mismatch surfaces as a queryable gold table and a dashboard panel; nothing is blocked,
alerted, or paged.

## User Stories

1. As the platform operator, I want to know when a firm's `advFilingData`-derived private
   fund count doesn't match SEC's independently-published Firm Roster aggregate count, so
   that I can investigate parsing gaps or rolling-window coverage issues before they
   compound silently.
2. As the platform operator looking at the dashboard, I want a single summary metric
   ("N firms mismatched, X%") visible without writing a query, so that I notice a
   regression in ADV data completeness the same way I'd notice any other pipeline health
   metric.
3. As an analyst querying gold directly, I want a table I can filter to just the
   mismatched firms with both counts side by side, so that I can decide which ones are
   worth investigating first (e.g., largest absolute or relative gap).
4. As the platform operator, I want the Firm Roster fetch to reuse the exact
   local-check-first, cost-nothing-most-days pattern the `advFilingData` fetch already
   uses, so that this doesn't add meaningful daily runtime or SEC traffic for a source
   that only changes monthly.
5. As the platform operator, I want a Firm Roster parsing or fetch failure to never affect
   MDM entity resolution, graph sync, or the existing `advFilingData` ingestion path, so
   that a bug in this purely-additive cross-check can never regress the platform's actual
   adviser/fund data.
6. As a future engineer extending this cross-check (e.g., adding more Firm Roster
   columns), I want the parser scoped narrowly to what's actually consumed today, so that
   I'm not maintaining ~440 undocumented columns (no SEC data dictionary exists for this
   format) with no current reader.

## Implementation Decisions

- **Two new Snowflake passthrough source tables, both mirroring the existing
  `SEC_SUBSIDIARY_EVIDENCE` "Agent neighborhood evidence" pattern** (raw silver rows
  exported straight through, not the dimensional `fact_key`/`company_key` modeling
  `PRIVATE_FUNDS` uses):
  - `SEC_ADV_FIRM_ROSTER` — new. CRD, `dataset_period`, and the ~8 documented aggregate
    private-fund columns from the Firm Roster CSV (private-fund flag, 7B(1)/7B(2) counts,
    hedge-fund count, total gross assets of private funds, etc. — the exact set ticket
    01's Q3 findings already documented). The remaining ~440 (registered) / ~163 (exempt)
    columns are not parsed or stored — no SEC data dictionary exists for them (ticket 01
    Q4) and nothing consumes them today.
  - `SEC_ADV_PRIVATE_FUND` — new, but not a new parser: a raw passthrough export of the
    *existing* `sec_adv_private_fund` silver table (already populated by the shipped
    `advFilingData` pipeline), carrying `adviser_crd_number`, `fund_index`, and
    `private_fund_id`. This is necessary because the existing Snowflake `PRIVATE_FUNDS`
    gold table (`_build_fact_adv_private_fund` in `serving/gold_models.py`) is CIK-keyed,
    not CRD-keyed — confirmed by reading its build query, which never selects
    `adviser_crd_number`. Without this second passthrough, there is no CRD-keyed fund
    count in Snowflake to reconcile against at all.
- **New silver-layer parser, mirroring `adv_bulk_ingest.py`'s existing shape**: a
  dataclass-based parser reading the Firm Roster CSV zip archives (`ia<date>.zip` /
  `ia<date>-exempt.zip`, per ticket 01's research), producing rows keyed by
  (`adviser_crd_number`, `dataset_period`) with `source_dataset_period`/`source_sha256`
  provenance columns matching every other ADV silver table's convention. Writes to a new
  `sec_adv_firm_roster` silver table (new `CREATE TABLE` in `silver_store.py`, new
  `ProtectedTablePolicy` entry in `silver_protection.py` keyed on
  `(adviser_crd_number, dataset_period)` — mirroring `sec_adv_private_fund`'s
  idempotency-protection pattern per CLAUDE.md's "SEC data idempotency" doctrine).
- **Registration in `ShardedSilverReader._TABLES`
  (`silver_support/sharded_reader.py`) is a required step, not optional** — CLAUDE.md
  documents a real, previously-shipped bug (the `INSTITUTIONAL_HOLDS`/`EMPLOYED_BY`
  5-whys) where a new silver table was added to schema and populated correctly, but
  omitted from this allowlist, causing MDM's cross-shard reader to silently treat it as
  "missing" rather than erroring. `sec_adv_firm_roster` must be added to this list in the
  same change that creates the table, with the same kind of regression test that
  incident's fix added (`test_sharded_silver_reader_exposes_thirteenf_filing_and_employment_event`
  is the precedent to follow).
- **Fetch and ingest follow the exact `fetch-adv-bulk`/`ingest-relationship-sources`
  pattern already shipped**, not a new command pair: `fetch-adv-bulk` (or a narrowly-added
  sibling entry point reusing its pure decision functions — `periods_to_fetch`,
  `select_downloadable`, etc. — for the Firm Roster's own monthly cadence) fetches the
  CSV zip, computes SHA-256, stages to S3, and writes a manifest entry with a new
  `kind: "iapd_firm_roster"`. `ingest-relationship-sources` (`warehouse_orchestrator.py`'s
  existing `kind`-dispatch block, which already branches on `"iapd_adv_bulk"` and
  `"sec_subsidiary_exhibit"`) gets one new `elif kind == "iapd_firm_roster":` branch
  calling the new parser's ingest function — the same generic manifest-consuming command,
  no new CLI surface for consumption.
- **Bronze persistence is correct here, per ADR 0002**: the ADR's "Bronze (narrowed)"
  table explicitly names "IAPD Form ADV Part 1 public bulk" as a source that gets bronze
  archived because it is not available via `edgartools` — the Firm Roster CSV is the same
  source family, so it follows the same already-decided bronze-persist-on-fetch pattern
  the `advFilingData` pipeline already uses, not a special case.
- **New dbt gold model, `adv_fund_count_reconciliation`**, alongside `private_funds.sql`
  in `infra/snowflake/dbt/edgartools_gold/models/gold/`: aggregates
  `SEC_ADV_PRIVATE_FUND` by `adviser_crd_number` (`COUNT(DISTINCT private_fund_id)`),
  joins against `SEC_ADV_FIRM_ROSTER`'s aggregate count for the same CRD and
  `dataset_period`, and computes a `mismatch` boolean column. Added to `sources.yml`
  (both new tables, passthrough-style entries matching `SEC_SUBSIDIARY_EVIDENCE`'s
  existing entry) and `gold.yml`, plus the corresponding bootstrap SQL (`CREATE TABLE`
  in `01_source_stage.sql`, merge-key registration in `03_source_load_wrapper.sql` for
  both new tables — merge key `(adviser_crd_number, dataset_period)` for both, matching
  how other composite-key passthrough tables like `SEC_EMPLOYMENT_EVENT` are registered).
- **Dashboard panel** in the existing Streamlit dashboard's "Pipeline" section
  (`infra/snowflake/streamlit/streamlit_app.py`'s `render_pipeline()`), following the
  same pattern already used there (`_render_pipeline_metrics` + a query-backed
  `st.metric`/dataframe pair, alongside the existing "Manifest task"/"Manifest copy"/
  "Gold dynamic table refresh" subsections): a summary metric ("N firms mismatched, X%")
  plus a filterable table of mismatched firms (CRD, firm name if available,
  `advFilingData`-derived count, Firm Roster count, delta).
- **Cadence**: Firm Roster fetch runs as part of the same daily invocation
  `fetch-adv-bulk` already gets wired into via the sibling
  [ADV fetch pipeline wiring spec](../adv-fetch-pipeline-wiring/spec.md) — no separate
  schedule. The reconciliation view recomputes on its own normal dynamic-table refresh
  schedule, same as every other `EDGARTOOLS_GOLD` table; no bespoke cadence control.
- **Never gates MDM/graph sync**: the new Stage this reuses already has a lenient `Catch`
  (per the sibling wiring spec) that falls through to `MdmRun` on failure — this applies
  identically to the Firm Roster fetch/ingest steps, since they share the same Stage and
  command surface as the `advFilingData` fetch.

## Testing Decisions

- **Parser**: pure-function unit tests mirroring `tests/application/test_adv_bulk_ingest.py`'s
  existing shape (feed a real or minimal synthetic Firm Roster CSV zip through the parser,
  assert on the returned dataclass rows) — no network, no Snowflake, no silver database
  needed for this layer.
- **Silver write + idempotency**: integration tests against a real `SilverDatabase`-backed
  DuckDB file, not a hand-rolled stub — CLAUDE.md's "Manifest-pipeline ownership +
  cursor-syntax incident" entry documents a real incident where a stub silently drifted
  from the actual schema and let a bug ship; any test exercising the new
  `ingest_adv_firm_roster_archive` path (especially the CRD/`dataset_period` primary-key
  and re-ingestion-is-a-no-op behavior) should use a real `SilverDatabase` fixture.
- **`ShardedSilverReader` registration**: a direct regression test following
  `test_sharded_silver_reader_exposes_thirteenf_filing_and_employment_event`'s exact
  pattern — build a real shard via `SilverDatabase`, write one row to
  `sec_adv_firm_roster`, assert `ShardedSilverReader` can read it back. This test must be
  written and confirmed to fail before the `_TABLES` entry is added (proving it would have
  caught the same class of bug the cited incident already shipped once) and pass after.
- **`ingest-relationship-sources` dispatch**: extend the existing test coverage for the
  `kind`-dispatch block in `warehouse_orchestrator.py` (wherever the existing
  `"iapd_adv_bulk"`/`"sec_subsidiary_exhibit"` branches are tested) with a
  `"iapd_firm_roster"` case, asserting the new parser is invoked and its row counts are
  reflected in `rows_written`.
- **Fetch wiring** (Firm Roster's own `periods_to_fetch`/`select_downloadable`-equivalent
  decision logic, and its manifest `kind` value): same seam as
  `tests/application/test_adv_bulk_fetch.py` already uses for `advFilingData` — pure
  functions, fake `fetch_metadata`/`fetch_archive`/`upload` callables, no real network or
  S3 calls needed.
- **dbt reconciliation model**: a dbt unit test in a new
  `_adv_fund_count_reconciliation_unit_tests.yml`, following the existing
  `_financial_factors_unit_tests.yml`/`_financial_derived_unit_tests.yml` convention —
  given rows in `SEC_ADV_PRIVATE_FUND` and `SEC_ADV_FIRM_ROSTER` with a known
  count mismatch for one CRD and a known match for another, assert the `mismatch` column
  is `true`/`false` respectively. `dbt compile` validates the model has no SQL errors
  before this.
- **Dashboard panel**: no automated test seam exists in this repo for Streamlit UI
  (dashboards aren't unit tested elsewhere either). Per CLAUDE.md's UI-change convention,
  this should be manually smoke-tested in a browser against a dev Snowflake connection
  before considering the panel done — not covered by an automated test.
- **What makes a good test here**: test each layer at its own boundary (parser: bytes in,
  rows out; silver: rows in, idempotent DuckDB state out; dbt: source rows in, `mismatch`
  column out) rather than one end-to-end test spanning all of them — matches how the
  existing `advFilingData` pipeline's own tests are already split by layer.

## Out of Scope

- Any change to the `advFilingData` per-fund pipeline itself (`adv_bulk_ingest.py`,
  `sec_adv_private_fund`'s existing schema/parser) beyond adding the new
  `SEC_ADV_PRIVATE_FUND` passthrough export — the per-fund data and its parser are
  unchanged.
- Alerting, paging, or any mechanism that blocks or gates a pipeline run on a mismatch —
  explicitly ruled out by ticket 08's Answer; this is passive, queryable visibility only.
- Parsing the remaining ~440/163 undocumented Firm Roster columns — narrow scope only,
  per ticket 08's Answer; a future ticket if a real consumer emerges.
- The 2000–2024 historical Firm Roster archives, if any exist — this spec covers the
  ongoing monthly cadence only, matching the ADV Pipeline map's existing "no historical
  backfill" decision (ticket 02/03) for the rest of ADV data.
- The Step Function wiring that inserts the new fetch/ingest Stage into
  `load_history`/`daily_incremental` — covered by the sibling
  [ADV fetch pipeline wiring spec](../adv-fetch-pipeline-wiring/spec.md); this spec
  assumes that stage exists and the Firm Roster fetch is added to the same manifest/kind
  surface it already wires in.
- Per-fund identity reconciliation (matching individual funds between the two sources) —
  the Firm Roster CSV only has aggregate counts, so per-fund matching is not possible from
  this source; only count-level reconciliation is in scope.

## Further Notes

- This spec depends on, but does not require completion of, the sibling
  [ADV fetch pipeline wiring spec](../adv-fetch-pipeline-wiring/spec.md) — that spec wires
  the *existing* `advFilingData` fetch into `load_history`/`daily_incremental`'s new
  Stage; this spec's Firm Roster fetch should land in the same Stage once it exists, but
  the parser/silver/dbt/dashboard work here can be built and tested independently first
  (all of it is testable at the unit/dbt-compile level without any live Step Functions
  execution).
- The `SEC_ADV_PRIVATE_FUND` passthrough table (needed for CRD-keyed fund counts) is new
  scope this spec adds beyond what ticket 08's Answer described — that ticket assumed the
  existing `advFilingData`-derived gold data already supported a CRD-level join; tracing
  the actual `_build_fact_adv_private_fund` code during this spec's authoring found it
  does not (CIK-keyed only). This was confirmed with the user before finalizing this spec
  (see this session's scoping question on "Fund-count source").
