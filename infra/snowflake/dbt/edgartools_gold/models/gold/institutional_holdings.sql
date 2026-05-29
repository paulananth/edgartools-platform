-- INSTITUTIONAL_HOLDINGS: 13F institutional holdings per (cik, accession, holding_index).
--
-- Isolated DAG branch — zero ref() edges into the existing 9-table chain.
-- Adds qoq_change_shares (quarter-over-quarter change in shares held) and
-- ownership_rank_within_period (rank by market_value for same security+quarter).
--
-- Grain: one row per (cik, accession_number, holding_index).
{{ gold_model_config('INSTITUTIONAL_HOLDINGS') }}

with base as (
    select * from {{ source("edgartools_source", "SEC_THIRTEENF_HOLDING") }}
),

with_qoq as (
    select
        *,
        -- QoQ share change for same (cik, cusip) pair
        lag(shares_held) over (
            partition by cik, cusip
            order by period_of_report
        ) as shares_held_prior_quarter,
        -- Rank by market value within (cusip, quarter) — 1 = largest holder
        rank() over (
            partition by cusip, period_of_report
            order by coalesce(market_value, 0) desc
        ) as ownership_rank_within_period,
        -- Most-recent quarter flag per (cik, cusip)
        row_number() over (
            partition by cik, cusip
            order by period_of_report desc
        ) as cusip_recency_rank
    from base
)

select
    cik,
    accession_number,
    holding_index,
    period_of_report,
    cusip,
    issuer_name,
    security_title,
    security_class,
    -- Quantity
    shares_held,
    market_value,
    -- Derived
    case
        when shares_held_prior_quarter is not null
        then shares_held - shares_held_prior_quarter
    end as qoq_change_shares,
    case
        when shares_held_prior_quarter is not null and shares_held_prior_quarter <> 0
        then (shares_held - shares_held_prior_quarter) / shares_held_prior_quarter
    end as qoq_change_pct,
    ownership_rank_within_period,
    cusip_recency_rank = 1 as is_current_holding,
    -- Options
    put_call,
    discretion_type,
    voting_auth_sole,
    voting_auth_shared,
    voting_auth_none,
    parser_version,
    ingested_at
from with_qoq
