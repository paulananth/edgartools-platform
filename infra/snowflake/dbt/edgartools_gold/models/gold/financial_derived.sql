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
-- YoY growth (Stage 5): looked up via a self-join to `prior_year_values`,
-- which picks ONE canonical row per (cik, fiscal_period, fiscal_year) --
-- preferring each accession's own "current" period over a later filing's
-- "comparative" restatement of the same fiscal_year, with accession_number
-- desc as a final tiebreaker. This replaces the prior lag()-over-fiscal_year
-- approach, whose ordering became non-deterministic once a single accession
-- could contribute two rows (current + comparative) for the same
-- (cik, fiscal_period) -- every fiscal_year then appears at least twice,
-- tying lag()'s ORDER BY with no tiebreaker.
--
-- "Current period" is precomputed as `is_current_period` in `base` (the row
-- whose period_end is the max within that accession's
-- (cik, accession_number, fiscal_period) group) because Snowflake rejects a
-- window function inside the ORDER BY of `qualify row_number() over (...)`
-- -- the inner max() over() must be materialised as a plain column first.
--
-- The accession_number desc tiebreaker is an approximation of "most
-- recently filed": SEC accession numbers are dominated by a 10-digit
-- filer-agent prefix, not strictly chronological across filers. A true
-- filed_date-based tiebreaker is tracked as a follow-up (see TODOS.md).
{{ gold_model_config('FINANCIAL_DERIVED') }}

with base as (
    select
        d.*,
        (d.period_end = max(d.period_end) over (
            partition by d.cik, d.accession_number, d.fiscal_period
        )) as is_current_period
    from {{ source("edgartools_source", "SEC_FINANCIAL_DERIVED") }} d
),

prior_year_values as (
    select
        cik,
        fiscal_period,
        fiscal_year,
        revenue,
        ebitda,
        net_income
    from base
    qualify row_number() over (
        partition by cik, fiscal_period, fiscal_year
        order by
            is_current_period desc,
            accession_number desc
    ) = 1
),

with_growth as (
    select
        b.*,
        py.revenue as revenue_prior,
        py.ebitda as ebitda_prior,
        py.net_income as net_income_prior,
        {{ yoy_growth('b.revenue', 'py.revenue') }} as revenue_yoy_growth,
        {{ yoy_growth('b.ebitda', 'py.ebitda') }} as ebitda_yoy_growth,
        {{ yoy_growth('b.net_income', 'py.net_income') }} as net_income_yoy_growth
    from base b
    left join prior_year_values py
        on py.cik = b.cik
        and py.fiscal_period = b.fiscal_period
        and py.fiscal_year = b.fiscal_year - 1
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
