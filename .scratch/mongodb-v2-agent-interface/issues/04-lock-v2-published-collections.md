# Lock what v2 Mongo publishes

Type: grilling
Status: resolved
Blocked by: 02

## Question

Which documents are in v2: issuer Feature Screen rows, full issuer
Subject Bundle Read (features + `IS_INSIDER` + `EMPLOYED_BY` only),
coverage/READY status, or also Explore-only gold?

Do not widen v1 unavailable keys (holders, auditor, parent, ADV) unless
this ticket explicitly does. Sample 21-CIK factors vs full universe is
ticket 05 / 01, not this ticket.

Research 01/02: do **not** persist `build_subject_feature_screen` as one
universe document (63k rows ≈ 70–82 MiB > 16 MiB BSON). Options for 04
include nested issuer-bundle docs, per-CIK screen rows, or SQL-mirror
collections. Names/index DDL stay fog until this lock.

## Comments

- 2026-09-11 Q1 accepted **A**: v2 publishes Feature Screen (one document
  per CIK) + issuer Subject Bundle Read of v1 agent-grade sections
  (features, current `IS_INSIDER`, current `EMPLOYED_BY`) + coverage /
  READY / full watermark. Not Explore-only gold. Not ADV as agent-grade.
- 2026-09-11 Q2 accepted **A**: Bundle documents keep the
  `build_issuer_subject_bundle` envelope. Holders / auditor / parent
  are present with coverage `unavailable` and empty rows; ADV is
  `not_applicable`. Not agent-grade; not omitted; not widened.
- 2026-09-11 Q3 accepted **A**: Two collections. One nested issuer-bundle
  document per CIK; one Feature Screen document per CIK. Both carry full
  watermark + READY. No per-edge collection. No SQL-flat mirror.
  Database/collection names stay fog.

## Answer

v2 publishes two document kinds, not Explore gold:

1. **Issuer Subject Bundle Read** — one nested document per CIK in the
   `build_issuer_subject_bundle` envelope. Agent-grade content is As-Of
   features, current `IS_INSIDER`, and current `EMPLOYED_BY`. Holders /
   auditor / parent stay on the envelope as `unavailable` with empty
   rows; ADV is `not_applicable`. Not omitted, not widened.
2. **Subject Feature Screen** — one document per CIK (one screen row),
   never the whole-universe Python return (16 MiB).

Both carry the full Agent-Grade watermark plus READY. No per-edge
collection. No relational-mirror of the Snowflake SQL sketches.
Exact names and index DDL remain not-yet-specified.
