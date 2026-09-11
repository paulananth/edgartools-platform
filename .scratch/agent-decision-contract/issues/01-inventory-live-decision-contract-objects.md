# Inventory live Decision Contract objects

Type: research
Status: resolved
Blocked by: none

## Question

Against live production Snowflake (and AWS only as needed to reach it), what
Decision Contract, graph-pointer, and universe objects actually exist today,
and how do they differ from the in-repo SQL sketches?

Determine specifically:

1. Whether schema `EDGARTOOLS_DECISION` exists in prod, which tables/views it
   holds, and whether `DECISION_CONTRACT_PUBLICATION` has any READY rows.
2. Whether `NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER` exists and what
   generation it points at.
3. Whether `EDGARTOOLS_GOLD.MDM_COMPANY_ENTITY` exists with `tracking_status`,
   and how that compares to gold `COMPANY` tracking.
4. Whether `SUBJECT_FEATURE_SCREEN` / `SUBJECT_BUNDLE_READ_ISSUER` are
   deployed, empty, or absent.
5. Grants: which roles can SELECT the contract schema if it exists.

Use live `SHOW`/`DESCRIBE`/`COUNT` (or Terraform/SQL apply records if live
query is impossible) plus the files under
`infra/snowflake/sql/decision_contract/`. Save findings at
`.scratch/agent-decision-contract/research/01-live-decision-contract-objects.md`
and cite each claim to the query or source file.

## Answer

Live prod (`edgartools-prod` / `EDGARTOOLS_PROD`, 2026-09-10): `EDGARTOOLS_DECISION`
exists and is empty (bootstrap `15_decision_schema.sql` only; no
`DECISION_CONTRACT_PUBLICATION`, so no READY rows). `GRAPH_ACTIVE_POINTER`
points at `a573ebba-5820-49f2-8c40-43a4f538a79b` (activated 2026-08-22).
`MDM_COMPANY_ENTITY` has `tracking_status`; its 63,197 `active` CIKs match
gold `COMPANY` 1:1. `SUBJECT_FEATURE_SCREEN` and `SUBJECT_BUNDLE_READ_ISSUER`
are absent. Reader USAGE + future VIEW SELECT on `EDGARTOOLS_PROD_READER`
(inherited by dashboard_owner and SYSADMIN).

Findings: [research/01-live-decision-contract-objects.md](../research/01-live-decision-contract-objects.md)
