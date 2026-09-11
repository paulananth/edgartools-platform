# 01 — Publish the 19-key factor vector in prod gold

**What to build:** Prod gold As-Of Decision Features expose the locked 19
keys, including EBITDA, diluted EPS, and EBITDA margin, for every CIK that
already has derived rows. A Feature Screen bind can read those keys. This
does not add companies.

**Blocked by:** None — can start immediately.

**Status:** resolved

- [x] Live gold factor columns include all 19 locked keys (EBITDA, diluted EPS, and EBITDA margin among them).
- [x] Those three passthrough keys are populated from existing derived values, not left all-null.
- [x] Distinct CIK count on gold factors is unchanged from the current 21-CIK sample (this ticket does not backfill the universe).
- [x] Operating margin is not used as a stand-in for EBITDA margin.

## Answer

**Deployed and live-verified 2026-09-11.** Ran `dbt run --select
financial_factors --full-refresh` against prod (the SQL body itself —
`ebitda`/`eps_diluted`/`ebitda_margin` passthrough — was already merged in
PR #595's `e3b76435`; dynamic-table materializations don't pick up a SQL
body change without an explicit `--full-refresh`, per this repo's own dbt
convention).

Two real deploy-time bugs surfaced and were fixed before the refresh
succeeded, neither a design problem with the ticket itself:

1. `dbt run` failed with `Env var required but not provided:
   'DBT_SNOWFLAKE_WAREHOUSE'` — `gold_model_config.sql`/`silver_model_config.sql`
   call `env_var('DBT_SNOWFLAKE_WAREHOUSE')` with no default, unlike
   `profiles.yml`'s own default. Set explicitly
   (`EDGARTOOLS_PROD_REFRESH_WH`).
2. `dbt run` then failed with `Object 'EDGARTOOLS_PROD.EDGARTOOLS_GOLD.
   FINANCIAL_DERIVED' does not exist or not authorized` running as the
   dbt secret's default role (`ACCOUNTADMIN`). Both `FINANCIAL_FACTORS`
   and `FINANCIAL_DERIVED` are live-owned by `EDGARTOOLS_PROD_LOADER`
   (confirmed via `SHOW DYNAMIC TABLES`) — running the `CREATE OR REPLACE
   DYNAMIC TABLE` as `ACCOUNTADMIN` instead would have silently reassigned
   ownership away from `EDGARTOOLS_PROD_LOADER`, the exact
   ownership-drift trap CLAUDE.md's "Manifest-pipeline ownership" and
   "Streamlit-in-Snowflake ownership" incidents already document. Forced
   `DBT_SNOWFLAKE_ROLE=EDGARTOOLS_PROD_LOADER` to match the live owner
   instead of using the secret's default; refresh then succeeded (7.56s),
   ownership unchanged.

**Live verification (prod Snowflake, post-refresh):**

```
total_rows=5056  distinct_ciks=21
ebitda_nonnull=2392  eps_diluted_nonnull=3298  ebitda_margin_nonnull=2197
```

Sampled rows confirm `EBITDA_MARGIN` and `OPERATING_MARGIN` hold genuinely
different values per row (e.g. one row: -0.0666 vs -0.1250), not an alias.
`DESCRIBE TABLE` confirms all 19 `PURE_SEC_FEATURE_KEYS` are present
(directly or via the `roe`/`roa` ← `return_on_equity`/`return_on_assets`
alias, done at the Python layer per contract ticket 12).
