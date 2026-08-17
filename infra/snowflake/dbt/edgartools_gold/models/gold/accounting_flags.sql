-- ACCOUNTING_FLAGS: Annual auditor identity + forensic scores per 10-K filing.
--
-- Adds risk_tier classification derived from forensic score thresholds and
-- consecutive_auditor_years (number of years same auditor has been retained).
--
-- dbt-gold-silver-rewiring map, Ticket 05: `base` now reads dbt silver's
-- sec_accounting_flag via ref() instead of the Python-builder-populated
-- EDGARTOOLS_SOURCE mirror, reconstructing _build_fact_accounting_flag's
-- (gold_models.py) fact_key/company_key/fiscal_year_date_key/form_key
-- exactly -- kept isolated from Tickets 02-04 because sec_accounting_flag's
-- own silver model (models/silver/sec_accounting_flag.sql) carries the
-- separately-tracked forensic-score "last non-null wins" fix
-- (LAST_VALUE(...IGNORE NULLS) over beneish_m_score/altman_z_score/
-- piotroski_f_score, generate_silver_dbt_models.py's
-- _COALESCE_PRESERVING_COLUMNS) -- this rewire picks up that already-fixed
-- output automatically, not a stale pre-fix baseline. The with_tenure/
-- with_risk derivation below is unchanged dbt SQL, not part of the Python
-- builder being replaced -- it already ran downstream of `base`, whatever
-- `base` sourced from.
--
--   fact_key = hash(accession_number) -- single-field surrogate key, no
--     discriminator needed (accession_number is already this table's PK)
--   form_key = hash(form_type), falling back to hash('10-K') when
--     form_type IS NULL -- reproducing the original DuckDB
--     COALESCE(hash(form_type), hash('10-K')) exactly. Needs an explicit
--     CASE guard, not COALESCE: unlike DuckDB, Snowflake's HASH(NULL)
--     returns a real, deterministic, nonzero value, so COALESCE would never
--     actually fall through. form_type is NOT NULL in the silver DDL today
--     (silver_store.py: "always 10-K"), so this branch is currently
--     unreachable -- kept for exact behavioral parity with the Python
--     builder anyway, matching this map's established rigor.
--   fiscal_year_date_key = fiscal_year*10000 + 1231 -- a synthetic
--     "fiscal-year-end" YYYYMMDD-shaped int, not a real calendar date, so
--     this is direct arithmetic on the integer fiscal_year column, not the
--     date_key() macro (which operates on an actual DATE expression)
--
-- Grain: one row per (cik, accession_number).
{{ gold_model_config('ACCOUNTING_FLAGS') }}

with base as (
    select
        {{ surrogate_key(['accession_number']) }} as fact_key,
        cik as company_key,
        (fiscal_year * 10000 + 1231)::integer as fiscal_year_date_key,
        case
            when form_type is null then {{ surrogate_key(["'10-K'"]) }}
            else {{ surrogate_key(['form_type']) }}
        end as form_key,
        accession_number,
        cik,
        fiscal_year,
        period_end,
        form_type,
        auditor_name,
        auditor_pcaob_id,
        auditor_location,
        icfr_attestation,
        auditor_changed,
        beneish_m_score,
        altman_z_score,
        piotroski_f_score,
        parser_version,
        ingested_at
    from {{ ref('sec_accounting_flag') }}
),

with_tenure as (
    select
        *,
        -- Count consecutive years with same auditor (tenure measure)
        sum(case when not coalesce(auditor_changed, false) then 1 else 0 end) over (
            partition by cik
            order by fiscal_year
            rows between unbounded preceding and current row
        ) as consecutive_auditor_years,
        row_number() over (
            partition by cik
            order by fiscal_year desc
        ) as recency_rank
    from base
),

with_risk as (
    select
        *,
        -- Beneish M-score thresholds (Beneish 1999): < -2.22 safe, > -1.78 flagged
        case
            when beneish_m_score > -1.78 then 'high'
            when beneish_m_score between -2.22 and -1.78 then 'medium'
            when beneish_m_score < -2.22 then 'low'
            else 'unknown'
        end as beneish_risk_tier,
        -- Altman Z-score thresholds: > 2.99 safe, 1.81–2.99 grey, < 1.81 distress
        case
            when altman_z_score > 2.99 then 'safe'
            when altman_z_score between 1.81 and 2.99 then 'grey'
            when altman_z_score < 1.81 then 'distress'
            else 'unknown'
        end as altman_zone,
        -- Piotroski F-score: 0–2 weak, 3–6 neutral, 7–9 strong
        case
            when piotroski_f_score >= 7 then 'strong'
            when piotroski_f_score between 3 and 6 then 'neutral'
            when piotroski_f_score <= 2 then 'weak'
            else 'unknown'
        end as piotroski_strength
    from with_tenure
)

select
    fact_key,
    company_key,
    fiscal_year_date_key,
    form_key,
    -- Natural keys
    accession_number,
    cik,
    fiscal_year,
    period_end,
    form_type,
    -- Auditor identity
    auditor_name,
    auditor_pcaob_id,
    auditor_location,
    icfr_attestation,
    auditor_changed,
    consecutive_auditor_years,
    -- Forensic scores
    beneish_m_score,
    beneish_risk_tier,
    altman_z_score,
    altman_zone,
    piotroski_f_score,
    piotroski_strength,
    -- NOTE: audit_opinion (unqualified/qualified/adverse/disclaimer) is NOT
    -- carried here.  It requires parsing the auditor's report section of the
    -- 10-K, for which no validated extractor exists yet.  A forward migration
    -- will add the column in the same change that lands the extractor.
    -- Recency
    recency_rank = 1 as is_most_recent,
    parser_version,
    ingested_at
from with_risk
