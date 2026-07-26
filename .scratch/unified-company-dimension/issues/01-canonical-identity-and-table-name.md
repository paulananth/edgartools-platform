# 01 — Canonical identity and table name

Type: grilling
Status: resolved
Labels: needs-triage

## Question

For Option B (one gold company dimension with both CIK and MDM entity_id), what
is the **canonical table** consumers should read, and what is the **primary
identity** of a row?

Candidates already in the platform:

| Surface | Key | Producer |
| --- | --- | --- |
| `EDGARTOOLS_GOLD.COMPANY` | `company_key` (= CIK) | dbt DT ← SOURCE ← warehouse gold export |
| `EDGARTOOLS_GOLD.MDM_COMPANY` | `entity_id` | `mdm export` MERGE from Postgres |
| Graph `Company` node | entity_id / generation | `mdm sync-graph` |
| Bundle Subject (CONTEXT.md) | typically CIK | Decision Graph Bundle |

Decisions needed:

1. **Primary key of the unified row** — CIK-only, entity_id-only, or composite
   with a declared “join for agents” key?
2. **Canonical name** — keep `COMPANY`, keep `MDM_COMPANY`, or introduce a new
   name (e.g. `COMPANY_DIM` / `ISSUER`)?
3. **What happens to the loser name** after cutover — drop, view alias, or
   long-lived compatibility view?

## Context (do not re-derive without re-checking prod)

- Counts were nearly aligned after 2026-07-26 source-load fix (~32,968 vs
  ~32,970) but **schemas differ** (tracking_status, parent, valid_from/to on
  MDM side; last_sync_run_id / entity_type / sic_description on warehouse side).
- Filing gold (`FILING_DETAIL`, ownership, financials) joins on `company_key`.
- MDM relationships and graph edges join on `entity_id`.
- Agent language: **Bundle Subject** is “typically a company identified by
  CIK”; Decision Graph Bundle also needs entity/graph identity.

## Blocked by

None — can start grilling immediately.

## Acceptance (when resolved)

- Written answer under `## Answer` with: primary key, table name, and fate of
  old names.
- One-line gist linked from `map.md` Decisions so far.
- If glossary terms change, `CONTEXT.md` updated in the same session.

## Answer

1. **Primary key:** **CIK / `company_key`**. One row per CIK. `entity_id` is an
   attribute on that row (required/nullable and multi-match rules → issue 02).
2. **Canonical name:** **`EDGARTOOLS_GOLD.COMPANY`**. Extend this dim with
   `entity_id` + selected MDM attributes; do not rename the long-term surface
   to `MDM_COMPANY`.
3. **Fate of `GOLD.MDM_COMPANY`:** **Compatibility view (or thin projection),
   then drop** after consumers migrate. No permanent dual export of the same
   grain under two names.

Filing gold keeps `company_key` joins. MDM/graph handle is `entity_id` on the
same row. Implementation still deferred.

## Comments

- Opened 2026-07-26 from operator choice of Option B; **do not implement** in
  this ticket — design only.
- Resolved 2026-07-26 (grill): PK=CIK, name=`COMPANY`, MDM_COMPANY=compat then drop.
