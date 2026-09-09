# Company classification codes

## Destination

A decision on which industry classification system(s) beyond SIC (NAICS,
GICS, or another candidate) to add for MDM companies, backed by research
into feasibility, licensing, and where the actual per-company code data
would come from -- resolved to a chosen system (or an explicit "not
worth it" call) plus an integration shape. This map produces the
decision, not the implementation: a separate build effort follows once
the map is clear.

## Notes

- `sic_code`/`sic_description` are already fully wired end-to-end (silver
  -> MDM `mdm_company` -> gold `mdm_company.sql`), sourced directly from
  EDGAR submissions data. This map is NOT about wiring SIC for the first
  time -- confirmed via `edgar_warehouse/mdm/database.py`,
  `edgar_warehouse/mdm/resolvers/company.py`,
  `infra/snowflake/dbt/edgartools_gold/models/gold/mdm_company.sql`.
- Scope: companies only. Advisers/funds already have a separate,
  ADV-based business classification that isn't in question here.
- Decision only, not execution -- do not implement inside this map's
  tickets.
- GICS is proprietary (S&P/MSCI) -- licensing is a first-class research
  question, not an afterthought. NAICS is a free US Census Bureau
  standard, same openness class as SIC.

## Decisions so far

## Not yet specified

- Where the chosen classification would live (a new MDM company field
  mirroring `sic_code`, a separate lookup/crosswalk table, or a
  gold-layer-only derived column) -- depends on which system is chosen
  and whether it's a flat code or needs a hierarchy (NAICS is
  hierarchical: 2-6 digit sector/subsector/industry-group/industry/
  national-industry; GICS is similarly tiered).
- Migration/versioning shape if a new field is added alongside the
  existing `sic_code` -- additive column vs. broader redesign.

## Out of scope

- Adviser/fund classification (ADV's own business-type system) --
  confirmed working, not part of this effort's destination.
- Implementation of whichever system gets chosen -- a follow-up effort,
  not this map.
