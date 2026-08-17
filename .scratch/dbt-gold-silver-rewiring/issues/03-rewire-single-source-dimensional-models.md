# 03 — Rewire Gold's Single-Source Dimensional Models onto Silver

**What to build:** `company`, `filing_activity`, `filing_detail`,
`adviser_disclosures`, `adviser_offices`, `earnings_releases`,
`guidance_facts`, and `executive_records` read from dbt silver via `ref()`,
including whatever light joins and surrogate-key derivation each currently
performs in its Python builder (typically one source table, a hashed key
column, and — for `company` specifically — its existing left join onto the
MDM golden-record company entity, which stays exactly as-is).

**Blocked by:** 01, 02

**Status:** ready-for-agent

- [ ] All 8 models source exclusively via `ref()` from dbt silver, using
      Ticket 01's key macro for any hash-derived key column (`filing_key`,
      `form_key`, `fact_key`, etc.)
- [ ] The cutover validation standard passes for each table, including
      `company.sql`'s MDM entity enrichment join (`has_multi_match_mdm_entity`
      flag and all) producing identical output to today
- [ ] `dbt run --full-refresh` succeeds for each model against prod
