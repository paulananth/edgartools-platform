# Survey free/public serving options for the v2 relationship-edge layer

Type: research
Status: claimed
Blocked by: none

## Question

Scope locked 2026-09-19 (operator grilling on this map's reopening):
SPARQL/RDF is being evaluated **only for the relationship-edge half** of
the v2 layer (`IS_INSIDER`, `EMPLOYED_BY` — subject-predicate-object
edges), not the tabular As-Of Decision Features, which stay wherever
they already land (MongoDB, per tickets 01-08). The comparison is an
**open survey**, not narrowed to SPARQL-vs-MongoDB, bounded to the same
hard constraint that decided MongoDB: free-tier and publicly network-
reachable, no ongoing warehouse cost. Fail-closed watermark semantics
(the outcome — no silently-stale edge data) must be preserved, but the
mechanism may be RDF-native or option-native rather than copying Mongo's
exact `readiness_state`/`agent_grade` field shape.

Survey, citing primary sources with URLs and dates checked:

1. **SPARQL/RDF**: already covered by
   [Research: free/public SPARQL hosting](../agent-contract-query-interface-options/research/01-free-public-sparql-hosting.md)
   — summarize rather than re-research; flag the one unconfirmed lead
   (TriplyDB "first million triples free") if it's worth a direct check.
2. **Hosted property-graph DBs speaking Gremlin or Cypher**: Neo4j
   AuraDB Free, ArangoDB Oasis, TigerGraph Cloud, Amazon Neptune (confirm
   whether any tier is permanent-free vs. trial, same rigor as the
   SPARQL research). Note: this is a **v2 serving-layer** question,
   distinct in scope from ADR 0001's "no external Neo4j for the MDM
   graph" (that's about the platform's own graph, not a public v2 read
   target) — do not treat that prior ruling as covering this.
3. **GraphQL-over-HTTP** on a free-forever host serving the same edge
   data (e.g. a free-tier serverless function/API layer over a small
   free Postgres/SQLite, Hasura Cloud free tier, or similar) — is there
   a real permanently-free public option, and does GraphQL's query
   shape suit an LLM agent traversing `IS_INSIDER`/`EMPLOYED_BY` edges
   any better or worse than SPARQL (cite evidence; if none exists for
   GraphQL specifically, say so plainly).
4. **Plain REST/JSON over free static/object hosting** (e.g. S3 +
   CloudFront on the always-free tier, or GitHub Pages-style hosting) —
   pre-materialized per-issuer edge documents fetched by URL, no query
   language at all. Note this only works if the agent needs point
   lookups, not open-ended graph traversal; flag that tradeoff plainly,
   don't resolve it (that's the grilling ticket's job).
5. For every option that fails the free-tier + public-reachability
   filter, one line and move on — do not give it a full workup.

Do not provision anything. Do not implement anything. Do not decide
which option wins — that is a follow-on grilling ticket once this
survey lands.

Save findings at
`.scratch/mongodb-v2-agent-interface/research/09-relationship-edge-serving-survey.md`.

## Answer

