-- EXECUTIVE_RECORDS: DEF 14A executive compensation per (cik, accession_number, fiscal_year, exec_name).
--
-- Isolated DAG branch — zero ref() edges into the existing 9-table chain.
-- Adds comp_rank_within_filing (1 = highest paid exec for that filing and
-- fiscal year) and comp_pct_change_yoy (change between adjacent fiscal years
-- as reported in the same filing).
--
-- Source shape (PR-1 / Q3-D):
--   DIMENSIONAL — surrogate keys are derived here directly (dbt-gold-
--   silver-rewiring map, Ticket 03): fact_key = hash(cik, accession_number,
--   fiscal_year, exec_name) via surrogate_key()'s multi-arg form -- cik is
--   in the hash for the same reason filing_activity's is (one accession can
--   carry more than one cik); company_key = cik (identity);
--   fiscal_year_date_key = fiscal_year*10000 + 1231 (literal Dec-31
--   encoding, not a hash).
--
-- Grain: one row per (cik, accession_number, fiscal_year, exec_name).
--   fiscal_year joined the grain with Person Consumer Contract ticket 23: a
--   Summary Compensation Table lists three fiscal years per executive, and
--   the prior (accession_number, exec_name) key collided them once the
--   parser emitted the correct name on every row.
--
--   The derived columns are computed WITHIN one filing on purpose. A fiscal
--   year is reported by up to three consecutive proxies (its own, then as a
--   prior year in the next two), so any window over (cik, exec_name) ordered
--   by fiscal_year alone has ties across accessions and no tiebreaker; and a
--   restated prior-year figure need not equal the original. Partitioning by
--   accession_number makes every window tie-free (the grain is unique on it)
--   and keeps a YoY comparison between two figures the same filing reported.
{{ gold_model_config('EXECUTIVE_RECORDS') }}

with base as (
    select
        {{ surrogate_key(['cik', 'accession_number', 'fiscal_year', 'exec_name']) }} as fact_key,
        cik as company_key,
        (fiscal_year * 10000 + 1231)::integer as fiscal_year_date_key,
        accession_number,
        cik,
        fiscal_year,
        exec_name,
        exec_role,
        total_comp,
        base_salary,
        bonus,
        stock_awards,
        option_awards,
        non_equity_incentive,
        parser_version,
        ingested_at
    from {{ ref("sec_executive_record") }}
),

with_rank as (
    select
        *,
        -- Rank within filing and fiscal year by total_comp (1 = highest paid)
        rank() over (
            partition by cik, accession_number, fiscal_year
            order by coalesce(total_comp, 0) desc
        ) as comp_rank_within_filing,
        -- Prior fiscal year for the same exec, as reported in this filing
        lag(total_comp) over (
            partition by cik, accession_number, exec_name
            order by fiscal_year
        ) as total_comp_prior_year,
        lag(fiscal_year) over (
            partition by cik, accession_number, exec_name
            order by fiscal_year
        ) as fiscal_year_prior_row,
        -- accession_number breaks the fiscal_year tie deterministically, not
        -- chronologically: the same latest year is reported by more than one
        -- filing, and any one of them names the same role holder.
        row_number() over (
            partition by cik, exec_role
            order by fiscal_year desc, accession_number desc, exec_name
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
        when fiscal_year_prior_row = fiscal_year - 1
         and total_comp_prior_year is not null and total_comp_prior_year <> 0
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
