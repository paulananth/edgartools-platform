# 04 — `adv_fund_count_reconciliation` dbt model + dashboard panel

**Correction found while implementing ticket 03 (2026-07-28):** the join description
below ("for the same CRD and `dataset_period`") is not implementable as literally stated,
for two independent reasons discovered during ticket 03:

1. `SEC_ADV_PRIVATE_FUND`'s Snowflake merge key had to be corrected from the
   originally-stated `(adviser_crd_number, dataset_period)` to its real silver PK,
   `(accession_number, fund_index)` — `sec_adv_private_fund` has no `dataset_period`
   column (only `source_dataset_period`), and even aliased, that pair is not row-unique
   (one CRD reports many `fund_index` rows per period). `adviser_crd_number`/
   `source_dataset_period` still ride along as ordinary exported columns, just not as the
   merge key. See ticket 03's own file for the full correction.
2. **Bigger issue, specific to this ticket's join logic:** `advFilingData` (the source
   `SEC_ADV_PRIVATE_FUND` passthrough) is a **rolling delta of filing activity, ~17% of
   firms per month** (per the ADV Pipeline map's ticket 01/02 findings), not a
   full-universe snapshot like the Firm Roster CSV. A row's `source_dataset_period`
   reflects whichever month that firm's ADV filing last landed in — not the current
   roster month. Joining on period-equality would show ~83% of firms as spurious
   mismatches (or no match at all) purely from this cadence gap, independent of any real
   completeness issue this cross-check is meant to catch.

**Before implementing this ticket, resolve the join semantics explicitly** — plausible
options: (a) reconcile against each CRD's *latest known* fund count from
`SEC_ADV_PRIVATE_FUND` (`MAX(source_dataset_period)` per CRD, or a materialized "effective
set" view mirroring `adv_bulk_ingest.py`'s `reconstruct_effective_adv_set` logic) rather
than period-equality; or (b) join only on `adviser_crd_number` and treat
`SEC_ADV_FIRM_ROSTER.dataset_period` as the roster's own point-in-time context (no
`SEC_ADV_PRIVATE_FUND` period filter at all, since it isn't period-partitioned in any
meaningful reconciliation sense). This was not resolved during ticket 03 — flagged here so
whoever picks up ticket 04 does not build the literal-period-equality join as originally
written.

**What to build:** A new dbt gold model, `adv_fund_count_reconciliation`, alongside
`private_funds.sql` in `infra/snowflake/dbt/edgartools_gold/models/gold/`: aggregates
`SEC_ADV_PRIVATE_FUND` by `adviser_crd_number` (`COUNT(DISTINCT private_fund_id)`), joins
against `SEC_ADV_FIRM_ROSTER`'s aggregate count for the same CRD (see the corrected join
semantics above — NOT literal period-equality), and computes a `mismatch` boolean column.
Add both new sources to `gold.yml`.

Add a dashboard panel in the existing Streamlit dashboard's "Pipeline" section
(`infra/snowflake/streamlit/streamlit_app.py`'s `render_pipeline()`), following the
existing `_render_pipeline_metrics` + query-backed `st.metric`/dataframe pattern used
alongside "Manifest task"/"Manifest copy"/"Gold dynamic table refresh": a summary metric
("N firms mismatched, X%") plus a filterable table of mismatched firms (CRD, firm name if
available, `advFilingData`-derived count, Firm Roster count, delta).

This is purely additive visibility — per the ADV Pipeline map's standing requirement, it
never gates, alerts, or pages; nothing here blocks any other pipeline stage.

**Blocked by:** Ticket 03 (Snowflake passthrough exports) — the model needs both
`SEC_ADV_PRIVATE_FUND` and `SEC_ADV_FIRM_ROSTER` live in Snowflake to join against.

**Status:** ready-for-agent

- [ ] `adv_fund_count_reconciliation` model exists, compiles (`dbt compile`), and its
      `mismatch` column is covered by a dbt unit test in a new
      `_adv_fund_count_reconciliation_unit_tests.yml` (following the existing
      `_financial_factors_unit_tests.yml`/`_financial_derived_unit_tests.yml`
      convention) — given rows with a known count mismatch for one CRD and a known match
      for another, `mismatch` is asserted `true`/`false` respectively.
- [ ] The model is deployed to dev via `dbt run --select adv_fund_count_reconciliation
      --full-refresh` and confirmed queryable.
- [ ] The dashboard panel is added to `render_pipeline()` and manually smoke-tested in a
      browser against a dev Snowflake connection (no automated UI test seam exists in this
      repo, per CLAUDE.md's UI-change convention) — summary metric and filterable
      mismatch table both render correctly.
- [ ] All pre-existing dbt tests and Streamlit imports still pass/compile.
