-- EARNINGS_RELEASES: 8-K earnings press releases per (cik, accession_number).
--
-- Isolated DAG branch — zero ref() edges into the existing 9-table chain.
-- Adds recency_rank (most-recent flag for dashboard queries).
--
-- Grain: one row per (cik, accession_number).
--
-- NOTE: Guidance ranges, non-GAAP EPS, beat/miss flags, and the
-- eps_beat_streak window are NOT computed here.  The underlying silver
-- schema deliberately does not carry those columns because they require
-- either validated per-company guidance extraction or cross-period
-- comparison.  Both will land in a forward migration with population in
-- the same change.
{{ gold_model_config('EARNINGS_RELEASES') }}

with base as (
    select * from {{ source("edgartools_source", "SEC_EARNINGS_RELEASE") }}
),

with_recency as (
    select
        *,
        row_number() over (
            partition by cik
            order by fiscal_year desc, coalesce(fiscal_quarter, 5) desc
        ) as recency_rank
    from base
)

select
    cik,
    accession_number,
    filing_date,
    fiscal_year,
    fiscal_quarter,
    period_end,
    -- GAAP results (validated via edgartools EarningsRelease.get_key_metrics)
    revenue_gaap,
    net_income_gaap,
    eps_gaap_diluted,
    -- Presence flags
    has_non_gaap,
    has_guidance,
    -- Most-recent flag (for dashboard queries)
    recency_rank = 1 as is_most_recent,
    parser_version,
    ingested_at
from with_recency
