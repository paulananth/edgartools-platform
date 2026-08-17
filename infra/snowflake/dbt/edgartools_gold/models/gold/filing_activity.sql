{{ gold_model_config('FILING_ACTIVITY') }}

-- dbt-gold-silver-rewiring map, Ticket 01: filing_key was the pilot column
-- proving the surrogate_key() macro end-to-end.
--
-- Ticket 03: base now reads dbt silver (sec_company_filing) via ref()
-- instead of the Python-builder-populated EDGARTOOLS_SOURCE mirror. Every
-- other key column is now derived here too, matching
-- _build_fact_filing_activity (gold_models.py) exactly:
--   fact_key   = hash(accession_number)      -- same formula as filing_key,
--                                                so the two are numerically
--                                                equal, as they were before
--   company_key = cik (identity, not a hash)
--   date_key    = YYYYMMDD integer of filing_date (date_key() macro, not a
--                 hash)
--   form_key    = hash(form), 0 for a null form (matching the original
--                 COALESCE(..., 0)) -- an explicit CASE on `form IS NULL`,
--                 not COALESCE(surrogate_key(...), 0): confirmed live that
--                 Snowflake's HASH(NULL) returns a real, nonzero value
--                 (unlike DuckDB's, which the original code relied on
--                 propagating to NULL) -- COALESCE would never have fired
select
  {{ surrogate_key(['accession_number']) }} as fact_key,
  cik as company_key,
  {{ surrogate_key(['accession_number']) }} as filing_key,
  {{ date_key('filing_date') }} as date_key,
  case when form is null then 0 else {{ surrogate_key(['form']) }} end as form_key,
  accession_number,
  cik,
  form,
  filing_date,
  report_date,
  is_xbrl
from {{ ref("sec_company_filing") }}
