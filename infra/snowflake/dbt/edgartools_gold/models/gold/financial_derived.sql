-- FINANCIAL_DERIVED: Normalised financial metrics per (cik, accession, fiscal_period, period_end).
--
-- Isolated DAG branch — zero ref() edges into the existing 9-table chain.
-- Adds YoY growth rates, TTM (trailing-twelve-month) revenue/EBITDA/FCF,
-- and peer rank percentiles within SIC-4 groupings using Snowflake window functions.
--
-- Grain: one row per (cik, accession_number, fiscal_period, period_end). A
-- single accession can yield both a "current" and a "comparative prior
-- period" row for the same fiscal_period, distinguished by period_end —
-- see sec_financial_derived's silver PK.
--
-- NOTE: the YoY lag() windows below partition by (cik, fiscal_period)
-- ordered by fiscal_year. If two rows share (cik, fiscal_period,
-- fiscal_year) — e.g. a comparative row from one filing and a current row
-- from another filing reporting the same fiscal_year — lag() ordering
-- across those rows is non-deterministic. Not addressed here; flagged in
-- TODOS.md as a follow-up.
{{ gold_model_config('FINANCIAL_DERIVED') }}

with base as (
    select
        d.*,
        -- YoY growth (requires prior-year FY row for same CIK)
        lag(revenue) over (
            partition by d.cik, d.fiscal_period
            order by d.fiscal_year
        ) as revenue_prior,
        lag(ebitda) over (
            partition by d.cik, d.fiscal_period
            order by d.fiscal_year
        ) as ebitda_prior,
        lag(net_income) over (
            partition by d.cik, d.fiscal_period
            order by d.fiscal_year
        ) as net_income_prior
    from {{ source("edgartools_source", "SEC_FINANCIAL_DERIVED") }} d
),

with_growth as (
    select
        *,
        case
            when revenue_prior is not null and revenue_prior <> 0
            then (revenue - revenue_prior) / revenue_prior
        end as revenue_yoy_growth,
        case
            when ebitda_prior is not null and ebitda_prior <> 0
            then (ebitda - ebitda_prior) / ebitda_prior
        end as ebitda_yoy_growth,
        case
            when net_income_prior is not null and net_income_prior <> 0
            then (net_income - net_income_prior) / net_income_prior
        end as net_income_yoy_growth
    from base
)

select
    w.cik,
    w.accession_number,
    w.fiscal_year,
    w.fiscal_period,
    w.period_end,
    w.form_type,
    -- Income statement
    w.revenue,
    w.gross_profit,
    w.ebitda,
    w.ebit,
    w.net_income,
    w.eps_diluted,
    -- Balance sheet
    w.total_assets,
    w.total_liabilities,
    w.total_equity,
    w.cash_and_equivalents,
    w.total_debt,
    -- Cash flow
    w.operating_cash_flow,
    w.capex,
    w.free_cash_flow,
    -- Margins (0.0–1.0)
    w.gross_margin,
    w.ebitda_margin,
    w.net_margin,
    -- Returns
    w.roic,
    w.roe,
    w.roa,
    -- YoY growth
    w.revenue_yoy_growth,
    w.ebitda_yoy_growth,
    w.net_income_yoy_growth,
    -- NOTE: forensic scores (Beneish M / Altman Z / Piotroski F) are NOT
    -- denormalised here.  They are annual constructs computed cross-period
    -- in sec_accounting_flag — read them from the ACCOUNTING_FLAGS gold
    -- model joined on (cik, fiscal_year) when needed.
    w.parser_version,
    w.ingested_at
from with_growth w
