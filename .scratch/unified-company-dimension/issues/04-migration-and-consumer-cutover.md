# 04 — Migration order and consumer cutover

Type: grilling
Status: resolved
Labels: needs-triage

## Question

Once identity and attributes are decided, what is the safe cutover order?

Likely consumers:

- dbt gold models joining `company_key`
- Streamlit / SIS dashboards
- `mdm export` writer target (`EDGARTOOLS_GOLD.MDM_*`)
- Graph sync (reads `MDM` schema mirror, not necessarily GOLD)
- Subject bundle / manager bundle reads

## Blocked by

01, 02, 03

## Acceptance (when resolved)

- Ordered migration steps with rollback note.
- Explicit “not in this effort” list (e.g. person/security unify).

## Answer

**Cutover order (when implementing later):**

1. **Enrich `COMPANY`** (dbt or agreed gold path): left join MDM by CIK;
   add `entity_id`, `display_name`, explore/ops columns, multi-match flag.
2. **Compatibility:** make `GOLD.MDM_COMPANY` a view/projection over unified
   `COMPANY` (or thin projection matching old column names where possible).
3. **Migrate readers** (dashboards, any direct `MDM_COMPANY` SQL) to
   `COMPANY` or the view.
4. **Stop dual export:** remove / stop `mdm export` MERGE into
   `EDGARTOOLS_GOLD.MDM_COMPANY` as a separate golden-record table once
   consumers are clean. Graph mirror (`MDM` schema) is separate and out of
   this drop unless a follow-on ticket says otherwise.
5. **Drop** the compatibility view after a declared soak period.

**Rollback:** re-enable `mdm export` MERGE to a physical `MDM_COMPANY` and
revert dbt model to warehouse-only COMPANY if needed.

**Not in this effort:** person/security/fund/adviser unify; Postgres MDM
schema redesign; residual holds pipeline; agent contract expansion of
`entity_id`.

## Comments

- Resolved 2026-07-26 via grill (phased cutover, recommended order).
