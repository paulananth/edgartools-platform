# Apply current MDM schema to local PostgreSQL 16

Type: task
Status: resolved
Owner: Grok
Blocked by: none

## Question

Install the current runtime MDM schema onto the local PostgreSQL 16 instance
so later tickets can inspect live tables, grants, and seed data.

This is not Clean MDM implementation. The current model is a typed registry
plus separate domain tables (`company`, `adviser`, `person`, `security`,
`fund`, `audit_firm`). The proposed shared Company/Person identities with
governed profiles remain blocked on
[Set the Clean MDM identity, merge, and recovery policy](01-set-merge-stage-policy.md).

Use the existing `mdm migrate` path against
`postgresql://postgres:test@127.0.0.1:5432/mdm`. Record server version, applied
migrations, resulting tables, and seed counts. Do not copy production data.

## Comments

2026-09-17 — Claimed by Grok in `grok/clean-mdm-local-postgres` after the user
asked Wayfinder to read the data model and apply MDM tables to local Postgres.
The frontier grilling ticket remains Codex-claimed and is not this work.

## Answer

Applied the current runtime schema with `uv run edgar-warehouse mdm migrate`
as `postgres` against `postgresql://postgres:test@127.0.0.1:5432/mdm`.
Evidence: [local-mdm-schema-evidence.json](../local-mdm-schema-evidence.json).

Facts later tickets can use:

- PostgreSQL 16.15 in `edgartools-clean-mdm-pg16`, same image digest as the
  earlier ledger baseline.
- 38 public tables: the 19 `MDM_TABLES` members plus `mdm_audit_firm`, graph
  generation/partition, publication/lease/coverage/checkpoint tables, and the
  acquisition/registry ledger tables owned by `edgartools_acquisition_owner`
  / `edgartools_acquisition_registry_owner`.
- Seeded reference data only. Domain golden records are empty except 10
  audit-firm `mdm_entity` rows and matching `mdm_audit_firm` rows.
- Six entity types and eleven relationship types, including `IS_ENTITY_OF`
  (adviser→company) and `IS_PERSON_OF` (adviser→person). That is the current
  separate-identity model, not shared Company/Person identities.
- `application` exists as LOGIN. No production rows were copied.

This does not implement Clean MDM and does not satisfy
[Set the Clean MDM identity, merge, and recovery policy](01-set-merge-stage-policy.md).
