# Confirm live FINANCIAL_FACTORS bind versus locked 19 keys

Type: research
Status: resolved
Blocked by: none

## Question

Against live production Snowflake (`edgartools-prod` / `EDGARTOOLS_PROD`)
and the in-repo gold model on this branch, does gold `FINANCIAL_FACTORS`
already expose the 19 locked As-Of Decision Feature keys, and if not,
what is the exact remaining bind gap?

Determine specifically:

1. `DESCRIBE` / column list of `EDGARTOOLS_GOLD.FINANCIAL_FACTORS` and
   `EDGARTOOLS_GOLD.FINANCIAL_DERIVED`. Which of `ebitda`, `eps_diluted`,
   `ebitda_margin`, `return_on_equity`, `return_on_assets`, `roe`, `roa`
   exist live?
2. Row count, distinct CIK count, and FY versus non-FY period mix on
   `FINANCIAL_FACTORS`.
3. Compare live columns to:
   - `PURE_SEC_FEATURE_KEYS` and `GOLD_FEATURE_COLUMN_ALIASES` in
     `edgar_warehouse/serving/subject_feature_screen.py`
   - `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql`
     on this branch
   - [Bind v1 feature keys to gold FINANCIAL_FACTORS](../../agent-decision-contract/issues/12-bind-v1-feature-keys-to-gold-financial-factors.md)
4. Whether `FINANCIAL_DERIVED` already has the passthrough source columns
   so a dbt `--full-refresh` of `financial_factors` is sufficient, or
   whether derived/facts are also missing values.
5. Do not decide whether to run the refresh (that is
   [Lock the financial-factors refresh path](05-lock-financial-factors-refresh-path.md)).

Use `snow sql --connection edgartools-prod`. Do not use `snowconn`.
Read-only. Do not implement.

Save findings at
`.scratch/agent-decision-v1-inputs/research/01-live-financial-factors-bind.md`
and cite each claim to the query or source file.

## Answer

Live 2026-09-11 (`edgartools-prod`). Gold `FINANCIAL_FACTORS` still lacks
`EBITDA` / `EPS_DILUTED` / `EBITDA_MARGIN` (and has `RETURN_ON_EQUITY` /
`RETURN_ON_ASSETS`, not `ROE`/`ROA`). Gold `FINANCIAL_DERIVED` and silver
`SEC_FINANCIAL_DERIVED` already hold those passthrough columns with values
(e.g. derived `EBITDA` non-null 2,392 of 5,056). Branch `financial_factors.sql`
already selects them. A dbt `--full-refresh` of `financial_factors` is
enough for the **column** bind.

Coverage is a separate fact: only **21 CIKs** have any factor row (5,056
rows, 1,867 FY). Not a Decision Subject Universe fill.
[research](../research/01-live-financial-factors-bind.md)
