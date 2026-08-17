-- GUIDANCE_FACTS: structured guidance values (low/mid/high) per company
-- guidance revision (ERDP-02).
--
-- Gold Explore only — not pure-SEC Agent-Grade Decision Features (ADR 0001).
-- Isolated DAG branch — no ref() into ownership or fundamentals chains.
--
-- Source shape:
--   dbt-gold-silver-rewiring map, Ticket 03: reads dbt silver
--   (sec_guidance_fact) via ref() instead of the Python-builder-populated
--   EDGARTOOLS_SOURCE mirror. Unlike this batch's other seven models,
--   fact_key/company_key need no surrogate_key() derivation here at all --
--   edgar_warehouse.explore.guidance_facts.guidance_fact_key() computes and
--   stores them durably in sec_guidance_fact at write time (a genuine data
--   column in silver_store.py's DDL, not something gold recomputes per
--   refresh), so this stays a pure passthrough for both. SEC-derived rows
--   (source_system in sec_8k/sec_10q/sec_10k) come from
--   EarningsRelease.guidance table extraction; firm_manual rows are
--   CSV/Parquet overrides or supplements, coexisting via source_system in
--   the natural key (ERDP-02-05).
--
--   NOT a pure passthrough for accession_number specifically: silver's
--   sec_guidance_fact stores '' (not NULL) for firm_manual rows, a
--   NOT NULL DEFAULT '' PRIMARY KEY column constraint in silver_store.py's
--   DDL. _build_fact_guidance (the Python builder this replaces) always
--   translated it back to NULL at the gold layer via NULLIF(accession_number,
--   ''); this model must do the same in its final select below, or
--   firm_manual rows would surface accession_number = '' to gold consumers
--   instead of the documented nullable column.
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
    select * from {{ ref("sec_guidance_fact") }}
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
    nullif(accession_number, '') as accession_number,
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
