-- EXECUTIVE_RECORDS: DEF 14A executive compensation per (cik, accession_number, exec_name).
--
-- Isolated DAG branch — zero ref() edges into the existing 9-table chain.
-- Adds comp_rank_within_company (1 = highest paid exec for that filing) and
-- comp_pct_change_yoy using window functions over the (cik, exec_name) time series.
--
-- Source shape (PR-1 / Q3-D):
--   DIMENSIONAL — EXECUTIVE_RECORD source carries surrogate fact_key
--   (hash of accession+exec_name) plus COMPANY+DATE FKs.
--
-- Grain: one row per (cik, accession_number, exec_name).
{{ gold_model_config('EXECUTIVE_RECORDS') }}

with base as (
    select * from {{ source("edgartools_source", "EXECUTIVE_RECORD") }}
),

with_rank as (
    select
        *,
        -- Rank within filing by total_comp (1 = highest paid)
        rank() over (
            partition by cik, accession_number
            order by coalesce(total_comp, 0) desc
        ) as comp_rank_within_filing,
        -- YoY compensation change for same exec at same company
        lag(total_comp) over (
            partition by cik, exec_name
            order by fiscal_year
        ) as total_comp_prior_year,
        row_number() over (
            partition by cik, exec_role
            order by fiscal_year desc
        ) as role_recency_rank
    from base
)

select
    fact_key,
    company_key,
    fiscal_year_date_key,
    -- Natural keys
    accession_number,
    cik,
    fiscal_year,
    exec_name,
    exec_role,
    -- Compensation
    total_comp,
    base_salary,
    bonus,
    stock_awards,
    option_awards,
    non_equity_incentive,
    -- Derived
    comp_rank_within_filing,
    case
        when total_comp_prior_year is not null and total_comp_prior_year <> 0
        then (total_comp - total_comp_prior_year) / total_comp_prior_year
    end as comp_pct_change_yoy,
    -- NOTE: deferred_comp / other_comp / exec_person_entity_id / tenure_start_year
    -- are NOT carried here.  Person identity is resolved by MDM
    -- (mdm_relationship_instance.source_entity_id on the EMPLOYED_BY edge);
    -- tenure is computed by MDM's _derive_employed_by from the EMPLOYED_BY
    -- history and stored on the relationship's properties JSON; the two
    -- SCT comp columns are not currently extractable by edgartools'
    -- extract_summary_compensation.
    -- Most-recent role flag (for current-exec dashboards)
    role_recency_rank = 1 as is_current_role,
    parser_version,
    ingested_at
from with_rank
