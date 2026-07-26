# 02 — CIK ↔ entity_id join and disagreement rules

Type: grilling
Status: resolved
Labels: needs-triage

## Question

How does a unified company row get both identities, and what happens when they
disagree or one side is missing?

Scenarios to resolve:

1. MDM company exists, warehouse `COMPANY` row missing (or vice versa).
2. Two MDM entities share one CIK, or one MDM entity has no CIK.
3. CIK renumbering / entity merge (graph merge lineage already exists).
4. Tracking-status `inactive` / quarantined MDM company vs active filing CIK.

## Blocked by

01 — canonical identity and table name

## Acceptance (when resolved)

- Explicit join predicate(s) and null / multi-match policy for agent-grade vs
  explore.
- Whether unified dim is “inner join only” or “full outer with completeness
  flags.”

## Answer

1. **Base set:** warehouse / SOURCE `COMPANY` CIKs (left side).
2. **Join:** **left join** MDM company by CIK → `entity_id` (and MDM attrs).
3. **Warehouse-only CIK:** row remains; `entity_id` **null**.
4. **MDM-only company (no warehouse CIK):** **not** on `COMPANY` by default.
5. **Multi-match:** **one** deterministic `entity_id` + **multi-match flag**;
   never multiple rows per CIK.
6. **Inactive / quarantined MDM:** still attach `entity_id`; expose status
   columns; do not null out the link or drop the CIK row.

## Comments

- Resolved 2026-07-26 via grill (left join, multi-match pick+flag, keep
  entity_id when inactive/quarantined).
