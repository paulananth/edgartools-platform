-- dbt-gold-silver-rewiring map, Ticket 03: reads dbt silver
-- (sec_adv_office, joined to sec_adv_filing and sec_company_filing for
-- cik/date resolution) via ref() instead of the Python-builder-populated
-- EDGARTOOLS_SOURCE mirror, matching _build_fact_adv_office
-- (gold_models.py) exactly:
--   fact_key = hash(accession_number, 'office', office_index)
--   company_key = COALESCE(adv_filing.cik, company_filing.cik)
--   date_key = YYYYMMDD integer of COALESCE(company_filing.filing_date,
--     adv_filing.effective_date) -- date_key() macro, not a hash
--   geography_key = hash of the normalized state_or_country + normalized
--     country, NULL only when BOTH normalize to nothing -- matches
--     _geography_natural_key's "state|country" natural key (concatenation
--     replaced with a 2-arg hash; per Ticket 01, key values reset at
--     cutover, so byte-identical reproduction of the old concatenation
--     isn't required, only that identical (state, country) pairs collide
--     and different pairs don't)
{{ gold_model_config('ADVISER_OFFICES') }}

with base as (
    select
        o.accession_number,
        o.office_index,
        o.office_name,
        o.is_headquarters,
        coalesce(f.cik, c.cik) as cik,
        coalesce(c.filing_date, f.effective_date) as fact_date,
        {{ normalized_text('o.state_or_country') }} as geo_state_norm,
        {{ normalized_text('o.country') }} as geo_country_norm
    from {{ ref('sec_adv_office') }} o
    left join {{ ref('sec_adv_filing') }} f on f.accession_number = o.accession_number
    left join {{ ref('sec_company_filing') }} c on c.accession_number = o.accession_number
)

select
  {{ surrogate_key(['accession_number', "'office'", 'office_index']) }} as fact_key,
  cik as company_key,
  {{ date_key('fact_date') }} as date_key,
  case
    when geo_state_norm is null and geo_country_norm is null then null
    else {{ surrogate_key(["coalesce(geo_state_norm, '')", "coalesce(geo_country_norm, '')"]) }}
  end as geography_key,
  accession_number,
  office_index,
  office_name,
  is_headquarters
from base
