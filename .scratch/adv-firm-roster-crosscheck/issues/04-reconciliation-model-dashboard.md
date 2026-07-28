# 04 — `adv_fund_count_reconciliation` dbt model + dashboard panel

**What to build:** A new dbt gold model, `adv_fund_count_reconciliation`, alongside
`private_funds.sql` in `infra/snowflake/dbt/edgartools_gold/models/gold/`: aggregates
`SEC_ADV_PRIVATE_FUND` by `adviser_crd_number` (`COUNT(DISTINCT private_fund_id)`), joins
against `SEC_ADV_FIRM_ROSTER`'s aggregate count for the same CRD and `dataset_period`, and
computes a `mismatch` boolean column. Add both new sources to `gold.yml`.

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
