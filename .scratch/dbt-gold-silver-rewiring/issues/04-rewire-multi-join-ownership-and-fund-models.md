# 04 — Rewire Gold's Multi-Join Ownership and Fund Dimensional Models onto Silver

**What to build:** `ownership_activity`, `ownership_holdings`, and
`private_funds` — the three models whose current Python builders `UNION`
multiple silver tables and derive natural keys via text normalization (owner
CIK-or-name fallback, security-title normalization) — reimplemented as dbt
SQL sourcing directly from dbt silver's raw ownership/fund tables via
`ref()`. This is the real porting work in the batch: unlike Tickets 02/03,
there is no existing dbt SQL to lean on, and the natural-key derivation logic
currently lives only in Python (`_ownership_fact_source_rows`,
`_private_fund_natural_key` in `gold_models.py`) and has to be re-expressed
in SQL.

**Blocked by:** 01, 02, 03

**Status:** ready-for-agent

- [ ] All 3 models source exclusively via `ref()` from dbt silver's
      `sec_ownership_non_derivative_txn`, `sec_ownership_derivative_txn`,
      `sec_ownership_reporting_owner`, `sec_adv_private_fund`, and
      `sec_adv_filing` models
- [ ] The owner natural-key fallback (CIK when present, else normalized name)
      and security-title normalization logic produce identical output to
      today's Python builder for every existing row
- [ ] The cutover validation standard passes at real scale — this batch
      supplies the map's required large-table case (ownership data is one of
      the platform's higher-volume tables)
- [ ] `dbt run --full-refresh` succeeds for each model against prod
