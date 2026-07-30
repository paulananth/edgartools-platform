# Unified Company Dimension (Option B)

## Destination

Replace the dual analytics company surfaces (`EDGARTOOLS_GOLD.COMPANY` and
`EDGARTOOLS_GOLD.MDM_COMPANY`) with **one** gold company dimension that carries
both **SEC CIK / company_key** identity and **MDM entity_id**, so filing joins
and MDM/graph joins share a single canonical row per company without forcing
consumers to pick between two tables.

**Status:** design grilling complete; ticket 05 **claimed and applied to
prod** (2026-07-29) — a circularity gap in the original design was found and
resolved by ticket 06 before any code was written. Steps 1–3 are live in
prod: `EDGARTOOLS_GOLD.COMPANY` now carries `entity_id`/`display_name`/
`tracking_status`/`parent_company_entity_id` for all 32,970 rows (0
multi-match), and `MDM_COMPANY` is a compat view over the renamed
`MDM_COMPANY_ENTITY`. Only step 4 (drop the compat view after a soak period)
remains, deferred pending a soak-length decision — see ticket 05's Progress
section for the full applied-changes list, including a live-discovered
missing `CREATE VIEW` grant on `EDGARTOOLS_PROD_LOADER` that was fixed at
the root (`08_loader_role.sql`), not just patched ad hoc.

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
- [05 research](issues/05-research-findings.md) — live-state check (2026-07-29):
  both tables internally clean (32,970 rows each, no duplicate keys); the
  CIK↔entity_id join is currently a perfect 1:1 (0 multi-match, 0 orphans
  either side) — cleaner than the multi-match case ticket 02 designed for.
  `COMPANY` is dbt-managed (`company.sql`, plain pass-through); `MDM_COMPANY`
  is written by `export.py`'s MERGE path, not dbt.
- [06 resolved](issues/06-resolve-mdm-company-export-target-circularity.md) —
  ticket 05's plan was circular as scoped: `MDM_COMPANY` is the *only*
  Snowflake landing target for the MDM export, so once it becomes a compat
  view over the enriched `COMPANY`, `company.sql`'s join to it would be
  self-referential. Fixed by renaming the export's physical MERGE target to
  **`MDM_COMPANY_ENTITY`** *now* (not deferred to cutover) — `company.sql`
  joins that instead, freeing the `MDM_COMPANY` name for the compat view.
  Considered and rejected moving the target into `EDGARTOOLS_SOURCE`
  (confirmed live: zero MDM tables there today; that schema's whole contract
  is "one write mechanism, native S3 pull" — MDM's Postgres-MERGE export is a
  different mechanism entirely and mixing them would blur that boundary).
  Also rejected `RAW`/`STG_` naming (implies bronze/source-layer semantics
  this gold-schema table doesn't have) in favor of `_ENTITY`, matching the
  other 4 MDM export targets.

## Not yet specified (implementation detail)

- Exact multi-match priority order (confidence vs tracking vs entity_id) —
  currently 0 live cases; keep the flag as a safeguard, not exercised today.
- Soak period length before dropping `MDM_COMPANY` view.
- Whether graph `MDM` schema mirror writer changes (default: **no**).

## Out of scope

- Implementing the unified dim until a **task** ticket is claimed.
- Unifying person/security/fund/adviser gold tables.
- Putting `entity_id` on the Agent Decision Surface (rejected in 03).
- Ticket 20 residual holds pipeline changes.
