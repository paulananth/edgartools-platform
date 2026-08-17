-- dbt-gold-silver-rewiring map, Ticket 04: reads dbt silver
-- (sec_ownership_non_derivative_txn UNION ALL sec_ownership_derivative_txn,
-- joined to sec_company_filing, left-joined to
-- sec_ownership_reporting_owner) via ref() instead of the
-- Python-builder-populated EDGARTOOLS_SOURCE mirror, matching
-- _build_fact_ownership_holding_snapshot (gold_models.py) exactly: one row
-- per (accession_number, owner_index, security, direct/indirect) "holding
-- group", keeping only the most recent transaction in that group --
--   security_key is required here (unlike ownership_activity.sql's
--     optional security_key): a holding group with no real security_title
--     is dropped entirely by the `where` filter below, matching the
--     Python builder's own pre-filter, so security_key is never NULL by
--     the time it reaches the final select and needs no NULL guard
--   "most recent transaction" = QUALIFY ROW_NUMBER() ... = 1, ordered by
--     txn_index DESC (falling back to 0 when NULL) then derivative-over-
--     non-derivative, reproducing the Python builder's own tie-break
--     exactly (see the source comment there: "Same SQL rewrite pattern as
--     _build_fact_ownership_transaction")
{{ gold_model_config('OWNERSHIP_HOLDINGS') }}

with base as (
    select
        t.accession_number,
        cf.cik,
        cf.filing_date,
        o.owner_index,
        o.owner_cik,
        o.owner_name,
        t.txn_index,
        t.security_title,
        t.shares_owned_after,
        t.ownership_direct_indirect,
        false as is_derivative,
        {{ normalized_text('o.owner_name') }} as owner_name_norm,
        {{ normalized_text('t.security_title') }} as security_title_norm
    from {{ ref('sec_ownership_non_derivative_txn') }} t
    join {{ ref('sec_company_filing') }} cf on cf.accession_number = t.accession_number
    left join {{ ref('sec_ownership_reporting_owner') }} o
        on o.accession_number = t.accession_number and o.owner_index = t.owner_index
    union all
    select
        t.accession_number,
        cf.cik,
        cf.filing_date,
        o.owner_index,
        o.owner_cik,
        o.owner_name,
        t.txn_index,
        t.security_title,
        t.shares_owned_after,
        t.ownership_direct_indirect,
        true as is_derivative,
        {{ normalized_text('o.owner_name') }} as owner_name_norm,
        {{ normalized_text('t.security_title') }} as security_title_norm
    from {{ ref('sec_ownership_derivative_txn') }} t
    join {{ ref('sec_company_filing') }} cf on cf.accession_number = t.accession_number
    left join {{ ref('sec_ownership_reporting_owner') }} o
        on o.accession_number = t.accession_number and o.owner_index = t.owner_index
),

keyed as (
    select
        *,
        case
            when owner_cik is not null then 'cik:' || cast(owner_cik as varchar)
            when owner_name_norm is not null then 'name:' || owner_name_norm
            else null
        end as party_nk,
        cast(coalesce(cik, 0) as varchar) || '|' || security_title_norm as security_nk,
        nullif(trim(regexp_replace(coalesce(ownership_direct_indirect, ''), '[[:space:]]+', ' ')), '') as di_clean
    from base
    where security_title_norm is not null
      and shares_owned_after is not null
)

select
    {{ surrogate_key(['accession_number', 'owner_index', 'security_nk', "coalesce(di_clean, '')"]) }} as fact_key,
    cik as company_key,
    {{ date_key('filing_date') }} as date_key,
    case when party_nk is null then null else {{ surrogate_key(['party_nk']) }} end as party_key,
    {{ surrogate_key(['security_nk']) }} as security_key,
    accession_number,
    owner_index,
    shares_owned_after::double as shares_owned_after,
    di_clean as ownership_direct_indirect
from keyed
qualify row_number() over (
    partition by accession_number, owner_index, security_nk, di_clean
    order by coalesce(txn_index, 0) desc, case when is_derivative then 1 else 0 end desc
) = 1
