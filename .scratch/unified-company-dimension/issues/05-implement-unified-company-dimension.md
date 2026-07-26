# 05 — Implement unified COMPANY dimension

Type: task
Status: open
Labels: needs-triage
Blocked by: 01, 02, 03, 04

## Question / work

Implement Option B per resolved design in
`.scratch/unified-company-dimension/spec.md` and map decisions 01–04.

**Do not start until operator explicitly claims this ticket.**

## Scope (from design)

1. Enrich `EDGARTOOLS_GOLD.COMPANY` (dbt or agreed path): left join MDM by CIK;
   PK remains `company_key`; add `entity_id`, `display_name` (MDM-preferring),
   explore/ops columns (`tracking_status`, `parent_company_entity_id`, flags).
2. Replace physical `GOLD.MDM_COMPANY` with compatibility view/projection.
3. Migrate known readers; stop dual `mdm export` MERGE to GOLD.MDM_COMPANY.
4. Drop compat view after soak.
5. Agent Decision Surface: **no** `entity_id` / tracking / parent as Decision
   Features.

## Out of scope

- Graph `MDM` schema mirror redesign (unless unblocked separately).
- Person/security/fund/adviser unify.
- Residual holds pipeline.

## Acceptance

- Single CIK-keyed `COMPANY` with entity_id attribute.
- Filing gold joins still on `company_key`.
- Compat path for `MDM_COMPANY` during migration; dual export stopped.
- No agent-contract expansion of entity_id without a new ADR.
