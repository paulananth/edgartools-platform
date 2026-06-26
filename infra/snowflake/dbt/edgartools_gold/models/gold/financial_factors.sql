-- FINANCIAL_FACTORS: Accounting-only fundamental factors per financial period.
--
-- Grain: one row per (cik, accession_number, fiscal_period, period_end).
-- This model intentionally excludes price, market cap, and market-derived
-- ratios. Shares outstanding is included as an accounting disclosure.
{{ gold_model_config('FINANCIAL_FACTORS') }}

with base as (
    select
        d.*,
        (d.period_end = max(d.period_end) over (
            partition by d.cik, d.accession_number, d.fiscal_period
        )) as is_current_period
    from {{ ref("financial_derived") }} d
),

prior_fy_values as (
    select
        cik,
        fiscal_year,
        total_assets,
        shares_outstanding
    from base
    where fiscal_period = 'FY'
    qualify row_number() over (
        partition by cik, fiscal_year
        order by
            is_current_period desc,
            accession_number desc
    ) = 1
),

line_items as (
    select
        *,
        current_assets - current_liabilities as working_capital
    from base
)

select
    l.cik,
    l.accession_number,
    l.fiscal_year,
    l.fiscal_period,
    l.period_end,
    l.form_type,
    l.is_current_period,

    -- Base accounting inputs retained for coverage and factor debugging.
    l.revenue,
    l.total_assets,
    l.total_liabilities,
    l.total_equity,
    l.cash_and_equivalents,
    l.total_debt,
    l.operating_cash_flow,
    l.free_cash_flow,
    l.net_income,
    l.current_assets,
    l.current_liabilities,
    l.accounts_receivable,
    l.inventory,
    l.selling_general_admin_expense,
    l.retained_earnings,
    l.depreciation_amortization,
    l.property_plant_equipment_net,
    l.shares_outstanding,

    -- V1 accounting-only factors.
    l.working_capital,
    {{ safe_ratio('l.working_capital', 'l.total_assets') }} as working_capital_to_assets,
    {{ safe_ratio('l.current_assets', 'l.current_liabilities') }} as current_ratio,
    {{ safe_ratio('(l.current_assets - l.inventory)', 'l.current_liabilities') }} as quick_ratio,
    {{ safe_ratio('l.accounts_receivable', 'l.revenue') }} as receivables_to_revenue,
    {{ safe_ratio('l.inventory', 'l.total_assets') }} as inventory_to_assets,
    {{ safe_ratio('l.selling_general_admin_expense', 'l.revenue') }} as sga_to_revenue,
    {{ safe_ratio('l.retained_earnings', 'l.total_assets') }} as retained_earnings_to_assets,
    {{ safe_ratio('l.revenue', 'l.total_assets') }} as asset_turnover,
    {{ safe_ratio('l.total_debt', 'l.total_assets') }} as debt_to_assets,
    {{ safe_ratio('l.cash_and_equivalents', 'l.total_assets') }} as cash_to_assets,
    {{ safe_ratio('l.free_cash_flow', 'l.revenue') }} as free_cash_flow_to_revenue,
    {{ safe_ratio('(l.net_income - l.operating_cash_flow)', 'l.total_assets') }} as accruals_to_assets,
    case
        when l.fiscal_period = 'FY'
        then {{ yoy_growth('l.total_assets', 'py.total_assets') }}
    end as asset_growth_yoy,
    case
        when l.fiscal_period = 'FY'
         and l.shares_outstanding is not null
         and py.shares_outstanding is not null
        then l.shares_outstanding - py.shares_outstanding
    end as shares_outstanding_yoy_change,

    l.parser_version,
    l.ingested_at
from line_items l
left join prior_fy_values py
    on py.cik = l.cik
    and py.fiscal_year = l.fiscal_year - 1
