{{ gold_model_config('COMPANY') }}

-- Enriched per ticket 05 (.scratch/unified-company-dimension/issues/05-implement-unified-company-dimension.md):
-- left join the MDM golden-record company entity onto the CIK-keyed
-- warehouse COMPANY dimension. PK stays company_key/cik (ticket 01); MDM
-- attributes are additive. Ticket 02 resolved the CIK<->entity_id join as
-- single-pick + flag: live state is a perfect 1:1 today (0 multi-match, see
-- .scratch/unified-company-dimension/issues/05-research-findings.md), but the
-- row_number/flag guard stays in as a safeguard against a future re-run of
-- MDM entity resolution reintroducing one, not because it's exercised now.
--
-- dbt-gold-silver-rewiring map, Ticket 03: base now reads dbt silver
-- (sec_company) via ref() instead of the Python-builder-populated
-- EDGARTOOLS_SOURCE mirror. company_key = cik (never a hash -- the Python
-- builder derived it as a plain identity, so no surrogate_key() macro is
-- involved here). The MDM golden-record join below is untouched.
with mdm_company as (
  select
    entity_id,
    cik,
    canonical_name,
    tracking_status,
    parent_company_entity_id,
    row_number() over (partition by cik order by entity_id) as cik_rank,
    count(*) over (partition by cik) as cik_match_count
  from {{ source("mdm_export", "MDM_COMPANY_ENTITY") }}
  where cik is not null
)

select
  c.cik as company_key,
  c.cik,
  c.entity_name,
  c.entity_type,
  c.sic,
  c.sic_description,
  c.state_of_incorporation,
  c.fiscal_year_end,
  c.last_sync_run_id,
  m.entity_id,
  coalesce(m.canonical_name, c.entity_name) as display_name,
  m.tracking_status,
  m.parent_company_entity_id,
  coalesce(m.cik_match_count, 0) > 1 as has_multi_match_mdm_entity
from {{ ref("sec_company") }} c
left join mdm_company m
  on m.cik = c.cik
  and m.cik_rank = 1
