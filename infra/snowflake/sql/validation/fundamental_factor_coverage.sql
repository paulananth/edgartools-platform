-- Non-null coverage for accounting-only fundamental factor inputs and outputs.
--
-- Run in the target Snowflake database (dev or prod). This is intentionally
-- a reporting query, not a deployment gate.

with base as (
    select *
    from EDGARTOOLS_GOLD.FINANCIAL_FACTORS
),

metric_values as (
    select fiscal_period, period_end, 'input' as metric_group, 'current_assets' as metric_name, current_assets as metric_value from base
    union all select fiscal_period, period_end, 'input', 'current_liabilities', current_liabilities from base
    union all select fiscal_period, period_end, 'input', 'accounts_receivable', accounts_receivable from base
    union all select fiscal_period, period_end, 'input', 'inventory', inventory from base
    union all select fiscal_period, period_end, 'input', 'selling_general_admin_expense', selling_general_admin_expense from base
    union all select fiscal_period, period_end, 'input', 'retained_earnings', retained_earnings from base
    union all select fiscal_period, period_end, 'input', 'depreciation_amortization', depreciation_amortization from base
    union all select fiscal_period, period_end, 'input', 'property_plant_equipment_net', property_plant_equipment_net from base
    union all select fiscal_period, period_end, 'input', 'shares_outstanding', shares_outstanding from base
    union all select fiscal_period, period_end, 'factor', 'working_capital', working_capital from base
    union all select fiscal_period, period_end, 'factor', 'working_capital_to_assets', working_capital_to_assets from base
    union all select fiscal_period, period_end, 'factor', 'current_ratio', current_ratio from base
    union all select fiscal_period, period_end, 'factor', 'quick_ratio', quick_ratio from base
    union all select fiscal_period, period_end, 'factor', 'receivables_to_revenue', receivables_to_revenue from base
    union all select fiscal_period, period_end, 'factor', 'inventory_to_assets', inventory_to_assets from base
    union all select fiscal_period, period_end, 'factor', 'sga_to_revenue', sga_to_revenue from base
    union all select fiscal_period, period_end, 'factor', 'retained_earnings_to_assets', retained_earnings_to_assets from base
    union all select fiscal_period, period_end, 'factor', 'asset_turnover', asset_turnover from base
    union all select fiscal_period, period_end, 'factor', 'debt_to_assets', debt_to_assets from base
    union all select fiscal_period, period_end, 'factor', 'cash_to_assets', cash_to_assets from base
    union all select fiscal_period, period_end, 'factor', 'free_cash_flow_to_revenue', free_cash_flow_to_revenue from base
    union all select fiscal_period, period_end, 'factor', 'accruals_to_assets', accruals_to_assets from base
    union all select fiscal_period, period_end, 'factor', 'asset_growth_yoy', asset_growth_yoy from base
    union all select fiscal_period, period_end, 'factor', 'shares_outstanding_yoy_change', shares_outstanding_yoy_change from base
)

select
    current_database() as database_name,
    fiscal_period,
    metric_group,
    metric_name,
    count(*) as row_count,
    count_if(metric_value is not null) as non_null_count,
    round(100 * count_if(metric_value is not null) / nullif(count(*), 0), 2) as non_null_pct,
    max(period_end) as latest_period_end
from metric_values
group by fiscal_period, metric_group, metric_name
order by fiscal_period, metric_group, metric_name;
