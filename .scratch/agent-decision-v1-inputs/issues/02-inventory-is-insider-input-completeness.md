# Inventory live IS_INSIDER input completeness

Type: research
Status: resolved
Blocked by: none

## Question

What IS_INSIDER input actually exists today for v1 (graph-keyed current
edges with source accession), and where does identity or coverage break
before a Decision Contract can mark the section `present` / `empty` /
`unavailable`?

Determine specifically:

1. Active-graph `IS_INSIDER` edge count, distinct issuer (company) keys,
   distinct person keys, and whether edges carry a source accession.
   Use `GRAPH_ACTIVE_POINTER` (expected generation `ae0db138-...` unless
   it has moved).
2. Gold `OWNERSHIP_HOLDINGS` / `OWNERSHIP_ACTIVITY`: row counts, columns
   (especially any `OWNER_CIK` / `OWNER_NAME` / person id), distinct
   issuer CIKs.
3. Silver `SEC_OWNERSHIP_REPORTING_OWNER` (and related ownership tables
   if needed): row counts and identity columns gold dropped.
4. Overlap: how many distinct graph-insider issuers sit in gold
   `MDM_COMPANY_ENTITY` / `COMPANY` with `tracking_status = 'active'`
   (MDM-active; warehouse-active is bookkeeping and out of scope).
5. Compare to contract ticket 05: `present` = ≥1 current graph edge with
   source accession; gold-only strings are never `present`.
6. Do not decide whether gold must grow person columns (that is
   [Lock what usable identity means for v1 insiders and employment](04-lock-v1-insider-employment-usable-identity.md)).

Use `snow sql --connection edgartools-prod`. Read-only. Do not implement.

Save findings at
`.scratch/agent-decision-v1-inputs/research/02-is-insider-input-completeness.md`
and cite each claim to the query or source file.

## Answer

Live 2026-09-11, pointer `ae0db138-...`. Graph `IS_INSIDER`: 902 person→company
edges, all current, all with `SOURCE_ACCESSION`, `SOURCE_SYSTEM=ownership_filing`;
88 issuer CIKs (87 MDM-active). Ticket 05 `present` is satisfiable on those 87.

Gold `OWNERSHIP_HOLDINGS` 42,507 rows / 4,577 company keys: accession +
`OWNER_INDEX` only, no `OWNER_CIK`/`OWNER_NAME`. Silver
`SEC_OWNERSHIP_REPORTING_OWNER` 59,030 rows still has those identity columns.
Gold-only rows cannot mark `present`.
[research](../research/02-is-insider-input-completeness.md)
