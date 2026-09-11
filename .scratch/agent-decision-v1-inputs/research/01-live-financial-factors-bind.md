# Live FINANCIAL_FACTORS bind versus locked 19 keys

Date: 2026-09-11
Connection: `snow sql --connection edgartools-prod` / `EDGARTOOLS_PROD`
SQL: [01-live-financial-factors-bind.sql](01-live-financial-factors-bind.sql)
Raw: [01-live-financial-factors-bind.out](01-live-financial-factors-bind.out)

Last statement (`INFORMATION_SCHEMA.DYNAMIC_TABLES()` `TARGET_LAG`) failed
SQL compilation (`invalid identifier 'TARGET_LAG'`). All bind/count queries
succeeded.

## Live columns

Gold `FINANCIAL_FACTORS` does **not** have `EBITDA`, `EPS_DILUTED`,
`EBITDA_MARGIN`, `ROE`, or `ROA`. It does have `RETURN_ON_EQUITY`,
`RETURN_ON_ASSETS`, `OPERATING_MARGIN`, and `ROIC`.

Gold `FINANCIAL_DERIVED` **does** have `EBITDA`, `EPS_DILUTED`,
`EBITDA_MARGIN`, plus native `ROE` / `ROA` / `ROIC`. Silver
`SEC_FINANCIAL_DERIVED` matches that passthrough set.

Source: `INFORMATION_SCHEMA.COLUMNS` named-bind query in the `.out` file.

## Counts

| Object | Rows | Distinct CIK | FY rows | Non-FY rows |
| --- | ---: | ---: | ---: | ---: |
| Gold `FINANCIAL_FACTORS` | 5,056 | **21** | 1,867 | 3,189 |
| Gold `FINANCIAL_DERIVED` | 5,056 | 21 | 1,867 | 3,189 |
| Silver `SEC_FINANCIAL_DERIVED` | 5,056 | 21 | — | — |

Period mix on factors: FY 1,867 / Q3 1,136 / Q2 1,063 / Q1 990 (21 CIKs
each). Every factors row has at least one of the 16 currently-live contract
keys non-null (5,056 / 5,056).

Derived passthrough non-null (all 5,056 rows): `EBITDA` 2,392,
`EPS_DILUTED` 3,298, `EBITDA_MARGIN` 2,197. FY slice (1,867): 777 / 1,647 /
716. Silver collapse matches those totals.

## Bind versus the 19 locked keys

`PURE_SEC_FEATURE_KEYS` (19) in
`edgar_warehouse/serving/subject_feature_screen.py`: revenue, gross_profit,
ebitda, ebit, net_income, eps_diluted, total_assets, total_liabilities,
total_equity, cash_and_equivalents, total_debt, operating_cash_flow,
free_cash_flow, gross_margin, ebitda_margin, net_margin, roe, roa, roic.
Aliases: `roe`←`return_on_equity`, `roa`←`return_on_assets`. Do not map
`operating_margin`→`ebitda_margin`.

This branch's `financial_factors.sql` already selects `l.ebitda`,
`l.eps_diluted`, `l.ebitda_margin` from derived. Contract ticket 12
implemented that bind; prod gold has not picked up the SQL-body change
(dbt dynamic tables need `--full-refresh`).

| Contract key | Live `FINANCIAL_FACTORS` | Live `FINANCIAL_DERIVED` |
| --- | --- | --- |
| 16 name-identical keys (revenue … roic except the three below and roe/roa) | present | present |
| `roe` / `roa` | via `RETURN_ON_*` only (no `ROE`/`ROA` column) | native `ROE`/`ROA` |
| `ebitda` / `eps_diluted` / `ebitda_margin` | **missing columns** | present, populated |

## Remaining gap

1. **Column bind:** a dbt `--full-refresh` of `financial_factors` is
   sufficient to add the three missing columns. Derived (and silver) already
   hold the values. Facts are not the blocker.
2. **Coverage:** only **21 CIKs** have any factor row. That is not a column
   bind; it is a universe-coverage fact for later tickets (map NYS:
   coverage thresholds). Do not treat 5,056 rows as Decision Subject
   Universe coverage.

Does not decide whether to run the refresh (grilling ticket 05).
