# Spec (draft) — Unified Company Dimension

**Status:** design grilling complete — **not** ready-for-agent for
implementation until a task ticket is opened and claimed.

## Intent

Option B: one gold company dimension exposing both SEC CIK (`company_key`) and
MDM `entity_id` so warehouse filing analytics and MDM/graph analytics stop
maintaining parallel “company” tables that look redundant but mean different
things.

## Non-goals (until tickets resolve)

- No code, dbt, or export changes in the grilling phase.
- No unification of person/security/fund/adviser gold tables.
- No change to Ticket 20 residual holds pipeline.

## Tickets

| # | Issue | Type | Status |
| --- | --- | --- | --- |
| 01 | [Canonical identity and table name](issues/01-canonical-identity-and-table-name.md) | grilling | resolved |
| 02 | [CIK ↔ entity_id join and disagreement](issues/02-cik-entity-join-and-disagreement.md) | grilling | resolved |
| 03 | [Attribute ownership and agent surface](issues/03-attribute-ownership-and-agent-surface.md) | grilling | resolved |
| 04 | [Migration and consumer cutover](issues/04-migration-and-consumer-cutover.md) | grilling | resolved |
| 05 | [Implement unified COMPANY dimension](issues/05-implement-unified-company-dimension.md) | task | open (blocked on claim) |

## Design decisions (grilling complete)

- **PK:** CIK / `company_key`.
- **Name:** `EDGARTOOLS_GOLD.COMPANY`.
- **`MDM_COMPANY`:** compat view → drop after soak.
- **Join:** left join MDM by CIK; multi-match pick+flag; keep entity_id when
  inactive/quarantined.
- **Agent surface:** CIK (+ display_name path); **not** entity_id / tracking /
  parent.
- **Cutover:** enrich COMPANY → compat view → migrate readers → stop dual
  GOLD export → drop view.

## Frontier

Grilling complete. Next: optional ADR for design archive; implementation only
when a new **task** ticket is claimed.
