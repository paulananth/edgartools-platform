-- dbt-gold-silver-rewiring map, Ticket 03: reads dbt silver
-- (sec_company_filing) via ref() instead of the Python-builder-populated
-- EDGARTOOLS_SOURCE mirror, matching _build_dim_filing (gold_models.py):
-- filing_key/form_key are hash()-derived (surrogate_key() macro);
-- company_key = cik (identity); date_key is YYYYMMDD integer arithmetic
-- (date_key() macro), not a hash. form_key is 0 for a null form via an
-- explicit CASE on `form IS NULL`, not COALESCE(surrogate_key(...), 0):
-- confirmed live that Snowflake's HASH(NULL) returns a real, nonzero value
-- (unlike DuckDB's, which the original code relied on propagating to
-- NULL) -- COALESCE would never have fired.
{{ gold_model_config('FILING_DETAIL') }}

select
  {{ surrogate_key(['accession_number']) }} as filing_key,
  accession_number,
  cik,
  cik as company_key,
  form,
  case when form is null then 0 else {{ surrogate_key(['form']) }} end as form_key,
  filing_date,
  {{ date_key('filing_date') }} as date_key,
  report_date,
  is_xbrl,
  size
from {{ ref("sec_company_filing") }}
