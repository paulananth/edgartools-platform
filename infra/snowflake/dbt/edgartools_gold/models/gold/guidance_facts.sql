-- GUIDANCE_FACTS: structured guidance values (low/mid/high) per company
-- guidance revision (ERDP-02).
--
-- Gold Explore only — not pure-SEC Agent-Grade Decision Features (ADR 0001).
-- Isolated DAG branch — no ref() into ownership or fundamentals chains.
--
-- Source shape:
--   EDGARTOOLS_SOURCE.GUIDANCE_FACTS loaded from serving Parquet export
--   built by _build_fact_guidance() (edgar_warehouse.serving.gold_models)
--   from silver sec_guidance_fact. SEC-derived rows (source_system in
--   sec_8k/sec_10q/sec_10k) come from EarningsRelease.guidance table
--   extraction; firm_manual rows are CSV/Parquet overrides or supplements,
--   coexisting via source_system in the natural key (ERDP-02-05).
--
-- Grain: one revision row per
--   (cik, metric, fiscal_year, fiscal_quarter, as_of, accession_number,
--    is_non_gaap, source_system).
-- Current view: is_current = latest as_of (then ingested_at) per base key
--   (cik, metric, fiscal_year, fiscal_quarter, accession_number,
--    is_non_gaap, source_system) — mirrors EARNINGS_CALENDAR's revision
--   model. Multiple as_of snapshots are retained (not collapsed) to support
--   A02.3's "guide in force before print date" recipe.
{{ gold_model_config('GUIDANCE_FACTS') }}

with base as (
    select * from {{ source("edgartools_source", "GUIDANCE_FACTS") }}
),

ranked as (
    select
        *,
        row_number() over (
            partition by cik, metric, fiscal_year, fiscal_quarter,
                         accession_number, is_non_gaap, source_system
            order by as_of desc, ingested_at desc
        ) as as_of_rank
    from base
)

select
    fact_key,
    cik,
    ticker,
    company_key,
    accession_number,
    metric,
    period_type,
    fiscal_year,
    fiscal_quarter,
    period_end,
    value_low,
    value_mid,
    value_high,
    unit,
    currency,
    is_non_gaap,
    as_of,
    source_system,
    source_ref,
    excerpt,
    confidence,
    parser_version,
    ingested_at,
    as_of_rank = 1 as is_current
from ranked
