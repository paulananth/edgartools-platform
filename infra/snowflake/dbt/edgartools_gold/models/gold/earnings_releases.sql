-- EARNINGS_RELEASES: 8-K earnings press releases per (cik, accession_number).
--
-- Isolated DAG branch — zero ref() edges into the existing 9-table chain.
-- Adds recency_rank (most-recent flag for dashboard queries).
--
-- Source shape (PR-1 / Q3-D):
--   DIMENSIONAL — surrogate keys (fact_key, company_key, filing_date_key,
--   period_end_date_key, form_key) are derived here directly (dbt-gold-
--   silver-rewiring map, Ticket 03), matching _build_fact_earnings_release
--   (gold_models.py) exactly: fact_key = hash(accession_number);
--   company_key = cik (identity); filing_date_key/period_end_date_key are
--   YYYYMMDD integers (date_key() macro, not a hash), the latter NULL when
--   period_end is NULL; form_key = hash('8-K') -- a constant, since every
--   row in this table is by definition an 8-K earnings release.
--
-- Grain: one row per (cik, accession_number).
--
-- NOTE: Non-GAAP EPS, beat/miss flags, and the eps_beat_streak window are
-- NOT computed here.  The underlying silver schema deliberately does not
-- carry those columns because they require cross-period comparison.
-- Guidance ranges (revenue/EPS low/mid/high) landed as ERDP-02's separate
-- GUIDANCE_FACTS table, not as columns here — join on (cik, accession_number)
-- when has_guidance is true (see docs/er-guidance-facts.md §8.3).
{{ gold_model_config('EARNINGS_RELEASES') }}

with base as (
    select
        {{ surrogate_key(['accession_number']) }} as fact_key,
        cik as company_key,
        {{ date_key('filing_date') }} as filing_date_key,
        case
            when period_end is null then null
            else {{ date_key('period_end') }}
        end as period_end_date_key,
        {{ surrogate_key(["'8-K'"]) }} as form_key,
        accession_number,
        cik,
        filing_date,
        fiscal_year,
        fiscal_quarter,
        period_end,
        revenue_gaap,
        net_income_gaap,
        eps_gaap_diluted,
        has_non_gaap,
        has_guidance,
        parser_version,
        ingested_at
    from {{ ref("sec_earnings_release") }}
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
    fact_key,
    company_key,
    filing_date_key,
    period_end_date_key,
    form_key,
    -- Natural keys (retained for direct silver-bound queries)
    accession_number,
    cik,
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
