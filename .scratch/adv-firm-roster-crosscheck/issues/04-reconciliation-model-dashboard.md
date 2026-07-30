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

**Resolved 2026-07-28 — option (b), not (a):** option (a)'s "effective set" approach is
not faithfully implementable from `SEC_ADV_PRIVATE_FUND` alone.
`reconstruct_effective_adv_set` picks the latest **filing** per CRD from filing-level data
(`AdvBulkFiling`/`snapshot.filings`), then takes that filing's fund rows — but there is no
CRD-keyed filing-level table exported to Snowflake (only the fund-level
`SEC_ADV_PRIVATE_FUND` passthrough). `SEC_ADV_PRIVATE_FUND` only carries rows for filings
that reported at least one fund, so a CRD's most recent ADV filing that reports **zero**
funds leaves no row there at all — picking "latest row present" via
`MAX(source_dataset_period)` would silently select an older, stale nonzero-count filing for
any firm that has since wound down its funds, understating the true mismatch rate (a false
negative, in the same failure class this correction section already flagged for the
literal-period-equality join). The model instead uses the plain reading of the ticket's own
aggregation spec — `COUNT(DISTINCT private_fund_id)` across ALL historical rows for the
CRD, joined only on `adviser_crd_number` (no period filter) against
`SEC_ADV_FIRM_ROSTER`'s most recent `dataset_period` snapshot per CRD. This deliberately
over-counts (never under-counts) firms whose funds have since been fully wound down — an
acceptable, documented blind spot for a purely-additive completeness signal. See the
model's SQL header comment for the same writeup in context.

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

- [x] `adv_fund_count_reconciliation` model exists and its `mismatch` column is covered by
      a dbt unit test in a new `_adv_fund_count_reconciliation_unit_tests.yml` (following
      the existing `_financial_factors_unit_tests.yml`/`_financial_derived_unit_tests.yml`
      convention) — given rows with a known count mismatch for one CRD and a known match
      for another, `mismatch` is asserted `true`/`false` respectively (plus three
      additional edge-case tests: a zero-funds CRD absent from `SEC_ADV_PRIVATE_FUND` is a
      true negative, not a mismatch; multi-period `SEC_ADV_FIRM_ROSTER` rows use only the
      latest `dataset_period`; a null-`adviser_crd_number` roster row is excluded before the
      join rather than surfaced as a null-CRD row — caught by code review, since `gold.yml`
      declares `adviser_crd_number` `not_null` on this model but the original `latest_roster`
      CTE had no null-CRD guard). **Not fully closed**: `dbt compile`/`dbt test` require a
      live Snowflake connection (`DBT_SNOWFLAKE_*`) not available in this session —
      `dbt parse` (no live connection required) succeeds and confirms the model, sources,
      `gold.yml`, and the new unit-test YAML are all syntactically valid and resolve
      correctly; `dbt compile` was attempted and confirmed to require real credentials
      (fails with a connection error against a dummy account, not a syntax error). Run
      `dbt compile --select adv_fund_count_reconciliation` and
      `dbt test --select adv_fund_count_reconciliation` for the final signoff.
- [ ] The model is deployed to dev via `dbt run --select adv_fund_count_reconciliation
      --full-refresh` and confirmed queryable. **Not done this session** — requires a live
      dev Snowflake connection.
- [x] The dashboard panel is added to `render_pipeline()` (`_adv_fund_count_mismatches`,
      `_adv_fund_count_reconciliation_summary`, `_adv_reconciliation_mismatch_stats` in
      `infra/snowflake/streamlit/streamlit_app.py`): a summary metric ("N / total firms
      mismatched, X%") plus a filterable table of mismatched firms (CRD, roster dataset
      period, both counts, the delta, and the 7B(1)/7B(2) breakdown — no CRD-keyed
      firm-name join surface exists anywhere in gold today, so "firm name if available" is
      genuinely not available and is omitted rather than fabricated). Covered by 6 offline
      unit tests in `tests/architecture/test_snowflake_streamlit_financial_factors.py`
      (`AdvFundCountReconciliationTests`) asserting the query text, table target, mismatch
      filter presence/absence, delta column presence, and the stats helper's
      zero/empty/division-by-zero/normal cases. **Not done this session**: the actual
      browser smoke test against a live dev Snowflake connection (no automated UI test seam
      exists in this repo, per CLAUDE.md's UI-change convention) — the Python-level tests
      are the ceiling reachable without Snowflake credentials.
- [x] All pre-existing dbt tests (verified via `dbt parse`, not `dbt test` — see above) and
      Streamlit imports/tests still pass (`test_snowflake_streamlit_financial_factors.py`:
      17/17 passed, including the 6 new tests; `test_dashboard_deploy_evidence.py` and
      `test_dashboard_foundation_boundaries.py`: 31/31 passed).

**Code review findings fixed (2026-07-28, before commit):** (1) `latest_roster` lacked the
same `adviser_crd_number is not null` guard `filing_derived_counts` had, which could have
surfaced a null-CRD reconciliation row violating this model's own new `gold.yml` `not_null`
test — fixed, plus a regression unit test. (2) `_adv_fund_count_reconciliation` (the
mismatch-only query function) was misleadingly named like the file's other `_*_history`
helpers that return their full result set — renamed to `_adv_fund_count_mismatches`. (3)
The "What to build" section's named `delta` column was missing from both the model and the
dashboard table — added `fund_count_delta` to the model (`roster_fund_count -
filing_derived_fund_count`) and surfaced it in the dashboard, replacing the prior
`abs(filing_derived_fund_count - roster_fund_count)` inline sort expression. (4) The
model's `count(distinct coalesce(private_fund_id, accession_number || ':' || fund_index))`
was an undisclosed, untested deviation from the "plain `COUNT(DISTINCT private_fund_id)`"
both this file and the model's own header comment claimed — removed; `private_fund_id` is
guaranteed non-null by `adv_bulk_ingest.py`'s fail-closed parser, so the fallback key
guarded against a scenario that cannot occur.
