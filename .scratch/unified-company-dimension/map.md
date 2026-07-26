# Unified Company Dimension (Option B)

## Destination

Replace the dual analytics company surfaces (`EDGARTOOLS_GOLD.COMPANY` and
`EDGARTOOLS_GOLD.MDM_COMPANY`) with **one** gold company dimension that carries
both **SEC CIK / company_key** identity and **MDM entity_id**, so filing joins
and MDM/graph joins share a single canonical row per company without forcing
consumers to pick between two tables.

**Status:** design grilling **complete** — **do not implement** until an
implementation task ticket is claimed.

## Notes

- Triggered after prod gold source-load recovery (2026-07-26): both tables
  populated (~32,968 `COMPANY` vs ~32,970 `MDM_COMPANY`); user chose **Option B**
  (unify) over Option A (keep warehouse dim + join MDM by CIK ad hoc).
- Domain: edgartools-platform. Consult root `CONTEXT.md` before new terms.
  Agent Decision Surface / Bundle Subject / company_key language must stay
  coherent with ADRs `0001`, `0002`.
- Related but distinct: `.scratch/company-master-pipeline/` (capture/orchestration
  of company identity + fundamentals), not the gold dual-table problem.

## Decisions so far

- Product direction: **Option B** — one unified company dimension (CIK +
  entity_id). Confirmed by operator 2026-07-26; **implementation deferred**.
- [01 resolved](issues/01-canonical-identity-and-table-name.md) — PK=`company_key`
  (CIK); name=`EDGARTOOLS_GOLD.COMPANY`; `MDM_COMPANY` → compat view then drop.
- [02 resolved](issues/02-cik-entity-join-and-disagreement.md) — left join MDM
  onto warehouse COMPANY; multi-match single pick + flag; keep entity_id when
  inactive/quarantined (with status columns).
- [03 resolved](issues/03-attribute-ownership-and-agent-surface.md) — agent
  surface stays CIK-only (no entity_id); tracking/parent explore/ops;
  `display_name` prefers MDM canonical.
- [04 resolved](issues/04-migration-and-consumer-cutover.md) — phased cutover:
  enrich COMPANY → compat view → migrate readers → stop dual GOLD export →
  drop view after soak.

## Not yet specified (implementation detail)

- Exact multi-match priority order (confidence vs tracking vs entity_id).
- Soak period length before dropping `MDM_COMPANY` view.
- Whether graph `MDM` schema mirror writer changes (default: **no**).

## Out of scope

- Implementing the unified dim until a **task** ticket is claimed.
- Unifying person/security/fund/adviser gold tables.
- Putting `entity_id` on the Agent Decision Surface (rejected in 03).
- Ticket 20 residual holds pipeline changes.
