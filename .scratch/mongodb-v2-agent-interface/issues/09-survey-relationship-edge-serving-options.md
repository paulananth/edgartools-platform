# Survey free/public serving options for the v2 relationship-edge layer

Type: research
Status: resolved
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

**No surveyed option clears the free-tier + public-reachability bar as
cleanly as Atlas M0 already does; Mongo remains the only vetted store.**
Full detail: `.scratch/mongodb-v2-agent-interface/research/09-relationship-edge-serving-survey.md`.

- **SPARQL/RDF**: no vendor offers a confirmed permanently-free,
  bring-your-own-data, public SPARQL endpoint. The one lead (TriplyDB)
  stayed unconfirmed and its cited pricing domain is now dead. Only
  genuinely free-forever route is self-hosting Fuseki/Oxigraph — real
  infrastructure to run, not a vendor SaaS.
- **Hosted property-graph DBs**: none clear it cleanly. Neo4j AuraDB Free
  is closest (free forever, public by default, 200k nodes/400k rels) but
  **auto-deletes, unrecoverable, after 30 days idle** — a harder failure
  mode than Atlas M0's resumable pause. ArangoDB's managed cloud has no
  free tier; TigerGraph's only permanent-free option is self-hosted.
  Neptune is a 30-day trial regardless of query-language framing.
- **GraphQL-over-HTTP**: Hasura Cloud's Free plan is real and
  permanent, but is a query layer needing a backing free Postgres (Neon
  or Supabase), each with its own pause behavior. No LLM benchmark
  compares GraphQL against SPARQL/SQL/Cypher/MQL head-to-head.
  Standalone GraphQL benchmarks sit in the same rough low-accuracy band
  as SPARQL's few-shot number, not directly comparable.
- **Plain REST/JSON over static hosting** (S3, CloudFront, Cloudflare R2,
  Cloudflare Pages, GitHub Pages): real permanently-free candidates
  exist. But this shape only serves **point lookups by known key**
  (fetch one issuer's edges) — no reverse/multi-hop traversal (e.g.
  "which issuers is person X an insider of") without a second
  separately-published index — and a CDN in front introduces a
  fail-closed hazard (stale cached document served after the origin
  flips to `not_ready`) that the query-engine-backed options don't have.
- **LLM query-generation accuracy** (SM3-Text-to-Query, NeurIPS 2024,
  the one same-methodology cross-language benchmark found): SQL 47.05%,
  Cypher 34.45%, MongoDB 21.55%, SPARQL 3.3% zero-shot (~30% five-shot).
  A real cost against SPARQL specifically for an LLM-driven agent.
- **Cross-check confirmed**: `IS_INSIDER`/`EMPLOYED_BY` are **already**
  inside the existing Mongo projection today — embedded as
  `insiders.rows`/`employment.rows` on the `issuer_subject_bundle`
  document (ticket 04, data-contract.md), not a gap needing a home. The
  live question a follow-on decision has to answer is narrower than
  "where do edges live": whether a genuine access-pattern gap (reverse/
  multi-hop graph lookups Mongo's per-subject embedding doesn't serve)
  justifies a *second* store despite every surveyed option's downside,
  or whether v2 stays on Mongo alone. See
  [Decide whether the v2 layer needs a second relationship-edge store](10-decide-second-edge-store-need.md).
- Structural note: every family surveyed *can* carry a watermark/
  generation stamp and support in-place fail-closed hiding as a
  data-modeling choice — none is structurally incapable of it, except
  that CDN-fronted static hosting needs explicit TTL/invalidation
  handling to preserve that property.

