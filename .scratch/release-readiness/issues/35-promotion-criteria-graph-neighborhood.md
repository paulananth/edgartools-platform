# 35 — Product-ready promotion criteria for Graph neighborhood (F8)

Type: grilling
Status: resolved
Blocked by: 27

## Question

What is the complete, product-ready set of acceptance criteria that must all pass before Graph
neighborhood is promoted from Partial to Covered in the coverage matrix? Concrete platform
surface per the matrix footnote: Snowflake `GRAPH_NODES`/`GRAPH_EDGES`; MDM relationship
instances (`IS_INSIDER`, `EMPLOYED_BY`, `AUDITED_BY`, `HAS_PARENT_COMPANY`,
`INSTITUTIONAL_HOLDS`, ...); Subject Bundle sections `insiders`, `employment`, `auditor`,
`has_parent`. Matrix note: "Deep-dive neighborhood for one CIK; not multi-issuer industry
graph."

Note: this product spans multiple relationship types individually covered by this map's
tickets 04 (relationship eligibility at the release watermark) and 06 (full-chain launch gate,
strict inheritance/no-exclusion-valve). This ticket's checklist is about the ER-skill-facing
graph *read* contract (does an agent get a coherent, complete one-CIK neighborhood with the
fields it needs), not a restatement of the underlying per-relationship-type GO gates — read
tickets 04/06 before writing this so the two don't duplicate or contradict.

Write this as a numbered list of criteria (per-relationship-type coverage within the
neighborhood, edge/node freshness agreement with MDM, Bundle section completeness per
relationship, explicit scope boundary re: single-CIK vs. multi-issuer), each with a concrete,
checkable acceptance query or procedure, following the exact method and rigor of
`erdp-coverage-promotion` tickets 03–06 — grounded in real schema/code, cross-checked against
ticket 27's ER-skill survey findings for this product, adversarially stress-tested for what a
naive checklist would miss.

## Answer

Grounded in the live graph mirror (`NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES`/`MDM_GRAPH_EDGES`,
checked against both the active generation and the newer unactivated one) and ticket 27's F8
survey findings — alongside F7, the weakest-grounded of all 12 products: no skill anywhere
mentions auditor networks or parent/subsidiary chains at all, and the matrix's Partial marking
substantially outruns what any of the 9 skills' text actually supports.

1. **A real, live-confirmed gap: two of the four named relationship types have zero edges in
   any graph generation.** Queried every one of the 14 tracked generations
   (`NEO4J_GRAPH_MIGRATION.GRAPH_GENERATION`) for distinct `relationship_type` values on
   `MDM_GRAPH_EDGES`: only `MANAGES_FUND`, `EMPLOYED_BY`, `HOLDS`, `COMPANY_HOLDS`, `IS_INSIDER`
   have ever appeared. **`AUDITED_BY` and `HAS_PARENT_COMPANY` — two of the four relationship
   types the coverage matrix footnote explicitly names for this product — have never existed as
   an edge type in this graph, in any of its 14 generations, including the newest
   (`residual-full-20260726T010010Z`).** Notably, `audit_firm`-type **nodes** do exist (10 rows,
   live-checked) — auditor entities have been created/derived, but no edge connects them to the
   companies they audit. This is consistent with tickets 22/23 (Subsidiary Exhibit Ingestion,
   Auditor-Report Evidence Ingestion — both marked "execution complete" on this map) having
   built the source **evidence** pipelines without a corresponding graph-sync step ever landing
   these two relationship types as edges.
   Acceptance (currently failing): `SELECT DISTINCT relationship_type FROM MDM_GRAPH_EDGES` must
   include `AUDITED_BY` and `HAS_PARENT_COMPANY` with non-zero counts in the active generation.

2. **This product's real scope, per the Bundle contract and ticket 27's survey, is narrower than
   "graph neighborhood" implies — it's several separately-named sections, not one traversal.**
   `docs/subject-bundle-read.md` already documents `insiders`, `employment`, `auditor`,
   `has_parent` as **independent** sections (each with its own present/empty/unavailable
   coverage flag) — there is no single unified "neighborhood" object to promote. This ticket's
   criteria are therefore: does each already-named section resolve correctly for its own
   relationship type, not "does a multi-hop traversal work" (which ticket 27's survey confirms
   **no skill asks for** — zero textual basis anywhere for cross-company graph queries like
   "who else does this auditor also audit").

3. **`insiders` (`IS_INSIDER`) and `employment` (`EMPLOYED_BY`) sections are separately owned —
   do not duplicate ticket 33/37's criteria here.** `IS_INSIDER` (2,608 active edges) is ticket
   33's (F6) to verify; `EMPLOYED_BY` (51,697 active edges) is ticket 37's (F10). This ticket
   should not re-litigate either — only `auditor` and `has_parent` are genuinely this ticket's
   own scope, and both currently fail criterion 1.

4. **Single-CIK scope boundary, explicit per the matrix footnote.** "Deep-dive neighborhood for
   one CIK; not multi-issuer industry graph" — a promoted product must not be evaluated against
   any coverage-universe-wide traversal bar; every section is a per-subject lookup.

5. **`has_parent` scope restriction, per the existing Bundle contract.** Already documented:
   "Only when subsidiary inventory complete; scope `registrant_disclosed`" — the promoted
   product must not infer a parent chain beyond what's registrant-disclosed (Exhibit 21/8), even
   once `HAS_PARENT_COMPANY` edges exist; this is a correctness boundary to preserve, not relax,
   when criterion 1 is eventually fixed.

**Explicitly not required for promotion:** any multi-hop/cross-company graph traversal (no skill
asks for it); an `INSTITUTIONAL_HOLDS`-as-graph-edge criterion here — that belongs to ticket 34
(F7), and per that ticket's own finding, the relationship-type-naming question for
holdings-related edges is unresolved there, not duplicated here.

**Known residual risk:** criterion 1 is a hard, currently-failing gate with no workaround —
`auditor` and `has_parent` sections cannot be genuinely `present` for any subject today, only
`empty`/`unavailable`, regardless of how the rest of this checklist is written. Root-causing
*why* the graph-sync step for these two types was never run (a code gap, a config gap, or simply
never invoked) was not attempted in this ticket — flagging for a dedicated follow-up rather than
guessing.
