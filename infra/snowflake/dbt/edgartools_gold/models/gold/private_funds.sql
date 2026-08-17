-- dbt-gold-silver-rewiring map, Ticket 04: reads dbt silver
-- (sec_adv_private_fund, left-joined to sec_adv_filing and
-- sec_company_filing for cik/date resolution, same coalesce shape as
-- adviser_disclosures.sql/adviser_offices.sql) via ref() instead of the
-- Python-builder-populated EDGARTOOLS_SOURCE mirror, matching
-- _build_fact_adv_private_fund (gold_models.py) exactly:
--   fact_key = hash(accession_number, 'fund', fund_index) -- the 'fund'
--     discriminator via surrogate_key()'s multi-arg form, same shape as
--     adviser_disclosures.sql's 'disclosure' discriminator
--   company_key = COALESCE(adv_filing.cik, company_filing.cik)
--   date_key = YYYYMMDD integer of COALESCE(company_filing.filing_date,
--     adv_filing.effective_date)
--   private_fund_key = hash of the composite natural key
--     '<company_key or 0>|<normalized fund_name>|<normalized fund_type>|
--     <normalized jurisdiction>', NULL only when company_key AND all three
--     normalized text fields are absent -- unlike disclosure_category_key
--     (single-field, NULL when that one field is empty), this is a
--     4-field composite key that's NULL only when every field is empty,
--     matching _private_fund_natural_key's `if not any((issuer is not
--     None, name, fund_type_value, jurisdiction_value))` check exactly
{{ gold_model_config('PRIVATE_FUNDS') }}

with base as (
    select
        p.accession_number,
        p.fund_index,
        p.fund_name,
        p.fund_type,
        p.jurisdiction,
        p.aum_amount,
        coalesce(f.cik, c.cik) as cik,
        coalesce(c.filing_date, f.effective_date) as fact_date,
        {{ normalized_text('p.fund_name') }} as fund_name_norm,
        {{ normalized_text('p.fund_type') }} as fund_type_norm,
        {{ normalized_text('p.jurisdiction') }} as jurisdiction_norm
    from {{ ref('sec_adv_private_fund') }} p
    left join {{ ref('sec_adv_filing') }} f on f.accession_number = p.accession_number
    left join {{ ref('sec_company_filing') }} c on c.accession_number = p.accession_number
),

keyed as (
    select
        *,
        case
            when cik is null
                and fund_name_norm is null
                and fund_type_norm is null
                and jurisdiction_norm is null
            then null
            else
                cast(coalesce(cik, 0) as varchar) || '|' ||
                coalesce(fund_name_norm, '') || '|' ||
                coalesce(fund_type_norm, '') || '|' ||
                coalesce(jurisdiction_norm, '')
        end as private_fund_nk
    from base
)

select
    {{ surrogate_key(['accession_number', "'fund'", 'fund_index']) }} as fact_key,
    cik as company_key,
    {{ date_key('fact_date') }} as date_key,
    case when private_fund_nk is null then null else {{ surrogate_key(['private_fund_nk']) }} end as private_fund_key,
    accession_number,
    fund_index,
    aum_amount::double as aum_amount
from keyed
