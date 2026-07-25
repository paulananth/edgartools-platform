-- EARNINGS_CALENDAR: forward-looking expected earnings dates (ERDP-03).
--
-- Gold Explore only — not pure-SEC Agent-Grade Decision Features (ADR 0001).
-- Isolated DAG branch — no ref() into ownership or fundamentals chains.
--
-- Source shape:
--   EDGARTOOLS_SOURCE.EARNINGS_CALENDAR loaded from serving Parquet export
--   built by edgar_warehouse.explore.earnings_calendar /
--   write_earnings_calendar_to_serving_export.
--
-- Grain: one revision row per
--   (cik, fiscal_year, fiscal_quarter, source_system, as_of).
-- Current view: is_current = latest as_of (then ingested_at) per base key.
--
-- Not the same as EARNINGS_RELEASES.filing_date (reactive 8-K).
{{ gold_model_config('EARNINGS_CALENDAR') }}

with base as (
    select * from {{ source("edgartools_source", "EARNINGS_CALENDAR") }}
),

ranked as (
    select
        *,
        row_number() over (
            partition by cik, fiscal_year, fiscal_quarter, source_system
            order by as_of desc, ingested_at desc
        ) as as_of_rank
    from base
)

select
    fact_key,
    cik,
    ticker,
    company_key,
    fiscal_year,
    fiscal_quarter,
    expected_date,
    expected_time,
    timezone,
    session,
    status,
    period_end,
    accession_number,
    source_system,
    source_ref,
    as_of,
    ingested_at,
    as_of_rank = 1 as is_current
from ranked
