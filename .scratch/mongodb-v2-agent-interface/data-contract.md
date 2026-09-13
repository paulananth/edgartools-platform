# Mongo Decision Projection — data contract (draft)

Status: **accepted** 2026-09-11 (operator A). Not applied to Atlas yet.
Decision Contract Version: `"1"`.
Sources: tickets 03–05; `build_issuer_subject_bundle`;
`build_subject_feature_screen`; `evaluate_agent_grade`; MongoDB schema
design (embed data accessed together; 16 MiB hard cap; `$jsonSchema`).

This is the **v2 document contract**. It is not the v1 Snowflake Decision
Contract and not a second Agent System of Engagement.

## Access pattern (why this shape)

| Read | Grain | Collections hit |
| --- | --- | --- |
| Rank / filter issuers | one Feature Screen document per CIK | `subject_feature_screen` |
| Inspect one issuer | one nested bundle document | `issuer_subject_bundle` |
| Fail-closed hide | all docs whose watermark generation is not current READY | both |

M0: 100 ops/s. A single-issuer Agent-Grade Read must be **one `find`**.
Neighborhood edges (insiders, employment) are **embedded** (1:few, accessed
with the subject). Feature Screen is a **separate collection** because the
Python universe `rows[]` payload exceeds 16 MiB as one document.

## Database and collections

| Name | Role |
| --- | --- |
| Database `edgartools_decision` | v2 projection of Snowflake `EDGARTOOLS_DECISION` |
| `issuer_subject_bundle` | one nested Subject Bundle Read per CIK |
| `subject_feature_screen` | one Subject Feature Screen row per CIK |

No per-edge collection. No Explore-gold collection.

`_id` for both collections: BSON int CIK (same as Python
`bundle_subject_cik` / `rows[].cik`). Not zero-padded string, not ObjectId.

## Shared identity on every agent-grade document

Required on **both** collections (ticket 03: four-field pin is not enough):

| Field | Meaning |
| --- | --- |
| `decision_contract_version` | `"1"` |
| `agent_grade` | bool from `evaluate_agent_grade` |
| `readiness_state` | `agent_ready` \| `not_ready` (Snowflake display analogue) |
| `decision_watermark.business_date` | as-of business date |
| `decision_watermark.gold_run_id` | gold/feature as-of |
| `decision_watermark.graph_generation_id` | active graph pin |
| `decision_watermark.decision_contract_version` | same as envelope version |
| `decision_watermark.bronze_content_digest` | ordered-unique Bronze hash digest (mandatory when bronze persist used) |
| `decision_watermark.silver_completeness_ok` | bool |
| `decision_watermark.graph_parity_ok` | bool |
| `projected_from` | `"snowflake_decision_contract"` |
| `projected_at` | publisher timestamp (ISO-8601), not the watermark identity |

A document is **agent-grade for a v2 Trading Decision** only if
`agent_grade == true` **and** `readiness_state == "agent_ready"` **and**
every required watermark component is present. Otherwise the v2 agent
abstains.

## `issuer_subject_bundle`

Shape = `build_issuer_subject_bundle` return, plus the shared identity
above.

Top-level (Python keys kept):

- `bundle_subject_cik` (same value as `_id`)
- `bundle_kind`: `"issuer"`
- `agent_grade_reasons`: list of strings
- `include_neighborhood_history`: bool (v2 default false)
- `sections`

`sections` keys (always present; do not omit):

| Section | v2 agent-grade? | Coverage |
| --- | --- | --- |
| `insiders` | yes | present / empty / unavailable |
| `employment` | yes | present / empty / unavailable |
| `subject_features` | yes | FY + interim flags |
| `holders_of_subject` | no | `unavailable`, `rows: []` |
| `subject_as_manager_portfolio` | no | `unavailable`, `rows: []` |
| `auditor` | no | `unavailable`, `rows: []` |
| `has_parent` | no | `unavailable`, `rows: []` |
| `adv` | no | `not_applicable`, `rows: []` |

Embed `insiders.rows` and `employment.rows` (bounded 1:few). Do not
unbounded-embed 13F holder rows even if a later map widens that section.

Typical size: ~12 KiB BSON with 20 insiders + 30 employment (research 01).
Well under 16 MiB. Outlier issuers still embed; if a future issuer blows
16 MiB, that is a later outlier-pattern ticket, not v2.

## `subject_feature_screen`

Shape = **one element** of `build_subject_feature_screen()["rows"]`, plus
shared identity. Never the whole-universe Python return.

Fields:

- `cik` (same as `_id`)
- `fy_features` / `interim_features` — 19 `PURE_SEC_FEATURE_KEYS`
- coverage and period metadata as in the Python row
- shared watermark + `readiness_state`

Null ≠ zero. No market-price fields.

## Indexes (M0-aware)

Keep indexes few; they count against 0.5 GB.

| Collection | Index |
| --- | --- |
| both | `_id` unique (CIK) — default |
| both | `{ "readiness_state": 1, "decision_watermark.graph_generation_id": 1 }` — hide / pointer-move scan |
| `subject_feature_screen` | none beyond that for v2 rank-by-scan of a small READY set |

No text/search indexes on v2. No TTL (hide is publisher-driven, ticket 06).

## Validation

New collections: `$jsonSchema` with `validationLevel: "strict"` and
`validationAction: "error"` (empty collections). Required: `_id`,
`decision_contract_version`, `agent_grade`, `readiness_state`,
`decision_watermark`. Enum `readiness_state` to
`agent_ready` \| `not_ready`. Enum `decision_contract_version` to `"1"`.

Do not apply to Atlas until the operator accepts this draft **and** a
cluster exists.

## Publisher rule (ticket 06)

A separate publisher writes only after Snowflake READY. On pointer /
READY move it fail-closes **in place**: `readiness_state=not_ready` and
`agent_grade=false` on docs that do not match current READY. Payload
stays. No delete. No extra pointer collection.

## Auth (ticket 07)

Internet agents: one **read-only** SCRAM user in the connection string.
Publisher: a **separate write** user. Product OAuth later; do not put
auth fields on the documents.

## Out of this contract

- Snowflake remains v1 SoE
- Atlas ingest of bronze/silver
- ADV / holders / auditor / parent as agent-grade
- Explore gold
- Paid cluster as a prerequisite
