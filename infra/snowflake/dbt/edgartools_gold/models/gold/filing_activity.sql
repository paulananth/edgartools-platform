{{ gold_model_config('FILING_ACTIVITY') }}

-- dbt-gold-silver-rewiring map, Ticket 01: filing_key is the pilot column
-- proving the surrogate_key() macro end-to-end -- accession_number is
-- already selected in this same passthrough query, so this only replaces
-- filing_key's derivation, not the model's source (Tickets 02/03 rewire the
-- FROM clause onto silver directly).
select
  fact_key,
  company_key,
  {{ surrogate_key(['accession_number']) }} as filing_key,
  date_key,
  form_key,
  accession_number,
  cik,
  form,
  filing_date,
  report_date,
  is_xbrl
from {{ source("edgartools_source", "FILING_ACTIVITY") }}
