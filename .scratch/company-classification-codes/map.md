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

- [Research NAICS/GICS/alternative classification systems for MDM companies](issues/01-research-naics-gics-alternatives.md) — neither NAICS nor GICS is worth adding: GICS is proprietary end-to-end with no free/low-cost per-company data path at any scale (enterprise-quote-only, no self-serve tier); NAICS's taxonomy is free but SEC/EDGAR captures no NAICS data for MDM's company universe, and the public SIC-to-NAICS crosswalk is confirmed many-to-many, so a derived value would be an approximation, not sourced fact. Recommends deriving SIC's own native 4-tier hierarchy (Division/Major Group/Industry Group, already implicit in the `sic_code` EdgarTools has 100% coverage on) instead — same tier depth as GICS, zero license, zero new data source.
- [Confirm final classification approach](issues/02-confirm-final-approach.md) — user accepted the recommendation: derive SIC's own hierarchy, do not add NAICS or GICS. Map destination reached; closes the map.

## Not yet specified

- Where a derived SIC hierarchy (Division/Major Group/Industry Group)
  would live (new MDM company fields mirroring `sic_code`, or a
  gold-layer-only derived column) and the exact shape of the
  Division range-lookup table -- deferred to the follow-up build effort,
  out of scope for this (decision-only) map.

## Out of scope

- Adviser/fund classification (ADV's own business-type system) --
  confirmed working, not part of this effort's destination.
- Implementation of whichever system gets chosen -- a follow-up effort,
  not this map.
