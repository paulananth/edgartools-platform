{{ config(alias='MDM_COMPANY', materialized='view') }}

-- Compat view (ticket 05, step 2:
-- .scratch/unified-company-dimension/issues/05-implement-unified-company-dimension.md).
-- MDM_COMPANY was the physical golden-record export target; ticket 06 renamed
-- that physical table to MDM_COMPANY_ENTITY, freeing this name for a
-- byte-for-byte compatibility projection so any existing reader of
-- EDGARTOOLS_GOLD.MDM_COMPANY keeps seeing the identical 15-column shape and
-- values it always did, unaffected by COMPANY's own enrichment. No in-repo
-- reader was found (dashboards, dbt models) as of 2026-07-29 -- this exists
-- for external/ad-hoc consumers during the migration soak period (ticket 04
-- step 5; soak length not yet decided, see the unified-company-dimension map's
-- "Not yet specified").
select
  entity_id,
  cik,
  canonical_name,
  ein,
  sic_code,
  sic_description,
  state_of_incorporation,
  fiscal_year_end,
  ticker,
  primary_ticker,
  primary_exchange,
  tracking_status,
  parent_company_entity_id,
  valid_from,
  valid_to
from {{ source("mdm_export", "MDM_COMPANY_ENTITY") }}
