-- dbt-gold-silver-rewiring map, Ticket 04: reads dbt silver
-- (sec_ownership_non_derivative_txn UNION ALL sec_ownership_derivative_txn,
-- joined to sec_company_filing for form/filing_date and left-joined to
-- sec_ownership_reporting_owner for the owner) via ref() instead of the
-- Python-builder-populated EDGARTOOLS_SOURCE mirror, matching
-- _build_fact_ownership_transaction (gold_models.py) exactly:
--   fact_key = hash(accession_number, owner_index, txn_index, 'D'/'N') --
--     the is_derivative discriminator via surrogate_key()'s multi-arg form,
--     same shape as the accession_number/owner_index/txn_index/derivative
--     tuple the Python builder concatenated
--   party_key = owner natural-key fallback: 'cik:<owner_cik>' when present,
--     else 'name:<normalized owner_name>', else NULL -- NOT the normalized
--     text itself; the 'cik:'/'name:' prefix distinguishes a CIK-shaped key
--     from a name-shaped one that happens to look like a CIK
--   security_key = '<company_key or 0>|<normalized security_title>', NULL
--     when the title has no real content after normalizing
--   ownership_txn_type_key = hash of the cleaned (trimmed/collapsed, NOT
--     lowercased -- transaction codes are case-significant single letters)
--     transaction_code, NULL when empty
--   form_key = hash(form) when form is present, else NULL (no 0 sentinel --
--     that pattern is specific to filing_activity.sql/filing_detail.sql's
--     own form_key, not this model)
{{ gold_model_config('OWNERSHIP_ACTIVITY') }}

with base as (
    select
        t.accession_number,
        cf.cik,
        cf.form,
        cf.filing_date,
        o.owner_index,
        o.owner_cik,
        o.owner_name,
        t.txn_index,
        t.security_title,
        t.transaction_code,
        t.transaction_shares,
        t.transaction_price,
        t.shares_owned_after,
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
        cf.form,
        cf.filing_date,
        o.owner_index,
        o.owner_cik,
        o.owner_name,
        t.txn_index,
        t.security_title,
        t.transaction_code,
        t.transaction_shares,
        t.transaction_price,
        t.shares_owned_after,
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
        case
            when security_title_norm is null then null
            else cast(coalesce(cik, 0) as varchar) || '|' || security_title_norm
        end as security_nk,
        nullif(trim(regexp_replace(coalesce(transaction_code, ''), '[[:space:]]+', ' ')), '') as txn_code_clean
    from base
)

select
    {{ surrogate_key(['accession_number', 'owner_index', 'txn_index', "case when is_derivative then 'D' else 'N' end"]) }} as fact_key,
    cik as company_key,
    {{ date_key('filing_date') }} as date_key,
    case when form is null then null else {{ surrogate_key(['form']) }} end as form_key,
    case when party_nk is null then null else {{ surrogate_key(['party_nk']) }} end as party_key,
    case when security_nk is null then null else {{ surrogate_key(['security_nk']) }} end as security_key,
    case when txn_code_clean is null then null else {{ surrogate_key(['txn_code_clean']) }} end as ownership_txn_type_key,
    accession_number,
    owner_index,
    txn_index,
    txn_code_clean as transaction_code,
    transaction_shares::double as transaction_shares,
    transaction_price::double as transaction_price,
    shares_owned_after::double as shares_owned_after,
    is_derivative
from keyed
