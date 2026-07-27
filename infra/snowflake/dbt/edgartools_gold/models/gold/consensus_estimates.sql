-- CONSENSUS_ESTIMATES: Street (or proxy) consensus statistics (ERDP-01).
--
-- Gold Explore only — not pure-SEC Agent-Grade Decision Features (ADR 0001).
-- Isolated DAG branch — no ref() into ownership or fundamentals chains.
--
-- Source shape:
--   EDGARTOOLS_SOURCE.CONSENSUS_ESTIMATES loaded from serving Parquet export
--   built by edgar_warehouse.explore.consensus_estimates /
--   write_consensus_estimates_to_serving_export.
--
-- Grain: one revision row per
--   (cik, metric, period_type, fiscal_year, fiscal_quarter, statistic,
--    as_of, source_system).
-- Current view: is_current = latest as_of (then ingested_at) per base key
--   (cik, metric, period_type, fiscal_year, fiscal_quarter, statistic,
--    source_system) — mirrors EARNINGS_CALENDAR / GUIDANCE_FACTS's
--    revision pattern.
--
-- Beat/miss vs actuals (EARNINGS_RELEASES / FINANCIAL_DERIVED) is computed
-- at query time by joining on as_of <= print_date; not stored here.
{{ gold_model_config('CONSENSUS_ESTIMATES') }}

with base as (
    select * from {{ source("edgartools_source", "CONSENSUS_ESTIMATES") }}
),

ranked as (
    select
        *,
        row_number() over (
            partition by cik, metric, period_type, fiscal_year, fiscal_quarter,
                         statistic, source_system
            order by as_of desc, ingested_at desc
        ) as as_of_rank
    from base
)

select
    fact_key,
    cik,
    ticker,
    company_key,
    metric,
    period_type,
    fiscal_year,
    fiscal_quarter,
    period_end,
    estimate_value,
    unit,
    currency,
    statistic,
    as_of,
    source_system,
    source_ref,
    ingested_at,
    as_of_rank = 1 as is_current
from ranked
