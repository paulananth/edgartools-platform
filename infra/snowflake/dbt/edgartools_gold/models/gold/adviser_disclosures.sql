-- dbt-gold-silver-rewiring map, Ticket 03: reads dbt silver
-- (sec_adv_disclosure_event, joined to sec_adv_filing and
-- sec_company_filing for cik/date resolution) via ref() instead of the
-- Python-builder-populated EDGARTOOLS_SOURCE mirror, matching
-- _build_fact_adv_disclosure (gold_models.py) exactly:
--   fact_key = hash(accession_number, 'disclosure', event_index) --
--     carries the same 'disclosure' discriminator the Python builder's
--     concatenated natural key used, via surrogate_key()'s multi-arg form
--   company_key = COALESCE(adv_filing.cik, company_filing.cik)
--   date_key = YYYYMMDD integer of COALESCE(company_filing.filing_date,
--     adv_filing.effective_date) -- date_key() macro, not a hash
--   disclosure_category_key = hash of the normalized (trim/collapse-space/
--     lower) disclosure_category, NULL when the category has no real
--     content (normalized_text() macro folds "empty after normalizing"
--     into NULL for this exact check)
{{ gold_model_config('ADVISER_DISCLOSURES') }}

with base as (
    select
        d.accession_number,
        d.event_index,
        d.disclosure_category,
        d.is_reported,
        coalesce(f.cik, c.cik) as cik,
        coalesce(c.filing_date, f.effective_date) as fact_date,
        {{ normalized_text('d.disclosure_category') }} as normalized_category
    from {{ ref('sec_adv_disclosure_event') }} d
    left join {{ ref('sec_adv_filing') }} f on f.accession_number = d.accession_number
    left join {{ ref('sec_company_filing') }} c on c.accession_number = d.accession_number
)

select
  {{ surrogate_key(['accession_number', "'disclosure'", 'event_index']) }} as fact_key,
  cik as company_key,
  {{ date_key('fact_date') }} as date_key,
  case
    when normalized_category is null then null
    else {{ surrogate_key(['normalized_category']) }}
  end as disclosure_category_key,
  accession_number,
  event_index,
  is_reported
from base
