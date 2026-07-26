# 03 — Attribute ownership and Agent Decision Surface

Type: grilling
Status: resolved
Labels: needs-triage

## Question

Which columns on the unified company dim are:

- **Agent Decision Surface** (Decision Features / Bundle Subject fields)?
- **Explore-only** (Human Explore System of Engagement)?
- **Operator-only** (tracking_status, quarantine, export watermarks)?

Warehouse-side fields today: entity_name, entity_type, sic, sic_description,
state_of_incorporation, fiscal_year_end, last_sync_run_id.

MDM-side fields today: canonical_name, ticker, primary_ticker, primary_exchange,
tracking_status, parent_company_entity_id, valid_from/to, EIN, …

## Blocked by

01, 02

## Acceptance (when resolved)

- Column ownership table with agent vs explore vs operator labels.
- Any new CONTEXT.md Decision Feature names written if required.

## Answer

| Column / concept | Agent Decision Surface | Explore / operator on `COMPANY` |
| --- | --- | --- |
| `company_key` / CIK | **yes** (Bundle Subject id) | yes |
| `entity_id` | **no** | yes (graph/MDM correlation) |
| `display_name` | yes (if name is agent-facing; MDM-preferring) | yes |
| warehouse SIC / fiscal_year_end / entity_type | existing filing-dim semantics (no change forced here) | yes |
| `tracking_status`, `parent_company_entity_id`, quarantine | **no** | yes |
| multi-match / completeness flags | no (unless later ADR) | yes |

Rules:

1. Agent subject identity stays **CIK**; `entity_id` is **not** agent contract.
2. `display_name` = MDM `canonical_name` when present else SEC/warehouse name.
3. Tracking/parent stay on dim for explore/ops only.

CONTEXT.md update deferred until implementation ADR (no glossary change required
for “display_name” until product ships agent-facing rename).

## Comments

- Resolved 2026-07-26 via grill.
