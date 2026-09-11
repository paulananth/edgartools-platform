# Inventory live EMPLOYED_BY input completeness

Type: research
Status: resolved
Blocked by: none

## Question

What EMPLOYED_BY input actually exists today for v1 (graph-keyed current
edges with source `proxy_def14a` or `item_5_02`), and where does identity
or coverage break before a Decision Contract can mark the section
`present` / `empty` / `unavailable` / `non_agent_grade`?

Determine specifically:

1. Active-graph `EMPLOYED_BY` edge count, distinct issuer keys, distinct
   person keys, and counts by source (`proxy_def14a` vs `item_5_02` vs
   other). Use `GRAPH_ACTIVE_POINTER`.
2. Silver `SEC_EMPLOYMENT_EVENT`: row counts, source/form columns,
   distinct CIKs.
3. Gold `EXECUTIVE_RECORDS`: row counts, columns, distinct CIKs. Flag
   pay-only rows that ticket 05 called `non_agent_grade`.
4. Overlap of graph-employment issuers with MDM-active gold companies.
5. Compare to contract ticket 05: `present` = ≥1 current graph edge with
   allowed source; pay-only gold is never `present`.
6. Do not decide the usable-identity bar (that is
   [Lock what usable identity means for v1 insiders and employment](04-lock-v1-insider-employment-usable-identity.md)).

Use `snow sql --connection edgartools-prod`. Read-only. Do not implement.

Save findings at
`.scratch/agent-decision-v1-inputs/research/03-employed-by-input-completeness.md`
and cite each claim to the query or source file.

## Answer

Live 2026-09-11, pointer `ae0db138-...`. Graph `EMPLOYED_BY`: 4,313
person→company edges (4,018 current), all with accession; 1,356 issuer CIKs
(1,351 MDM-active). Live `SOURCE_SYSTEM` is `item_502_filing` (4,268) and
`proxy_filing` (45) — **not** ticket 05's `item_5_02` / `proxy_def14a` tokens.
Literal-matching those tokens would mark every live edge not-`present`.

Silver `SEC_EMPLOYMENT_EVENT` 7,676. Gold `EXECUTIVE_RECORDS` 14,755 / 903
CIKs (all MDM-active) is pay sidecar (`non_agent_grade`).
[research](../research/03-employed-by-input-completeness.md)
