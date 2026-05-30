-- ACCOUNTING_FLAGS: Annual auditor identity + forensic scores per 10-K filing.
--
-- Isolated DAG branch — zero ref() edges into the existing 9-table chain.
-- Adds risk_tier classification derived from forensic score thresholds and
-- consecutive_auditor_years (number of years same auditor has been retained).
--
-- Source shape (PR-1 / Q3-D):
--   DIMENSIONAL — ACCOUNTING_FLAG source carries surrogate fact_key plus
--   COMPANY+DATE+FORM FKs.  auditor_name / auditor_pcaob_id retained as
--   natural-key columns; AUDIT_FIRM dim deferred until cross-firm analytics
--   demand emerges.
--
-- Grain: one row per (cik, accession_number).
{{ gold_model_config('ACCOUNTING_FLAGS') }}

with base as (
    select * from {{ source("edgartools_source", "ACCOUNTING_FLAG") }}
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
