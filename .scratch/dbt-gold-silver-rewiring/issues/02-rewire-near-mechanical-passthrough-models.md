# 02 — Rewire Gold's Near-Mechanical Passthrough Models onto Silver

**What to build:** `financial_facts`, `institutional_holdings`,
`financial_derived`, `financial_factors`, `adv_fund_count_reconciliation`,
and `ticker_reference` read from dbt silver via `ref()` instead of the
`EDGARTOOLS_SOURCE`-mirrored tables `gold_models.py`'s Python builders
currently populate. These six are the lowest-risk batch — each is either a
pure passthrough or already has its real business logic (YoY growth,
peer-rank percentiles, roster reconciliation) living in dbt SQL layered on
top of the Python passthrough today. This batch proves the `ref()` cutover
pattern end-to-end before the harder, multi-join tables in Ticket 04 follow.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] All 6 models source exclusively via `ref()` from dbt silver models;
      zero `source("edgartools_source", ...)` references remain for these six
      tables
- [ ] The cutover validation standard (digest-based Table-Specific
      Reconciliation, per the duckdb-retirement map's resolved Ticket 07)
      passes for each table against its current `EDGARTOOLS_SOURCE`-backed
      output — compared on business-key content, not surrogate-key columns,
      per Ticket 01's key-regeneration decision
- [ ] `dbt run --full-refresh` succeeds for each model against prod
- [ ] The corresponding `gold_models.py` Python builders for these 6 tables
      are left in place but unreferenced by any live path (removal happens in
      Ticket 07 of this batch, once every table has cut over)
