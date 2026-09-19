# Free/public serving options for the v2 relationship-edge layer

Ticket: `.scratch/mongodb-v2-agent-interface/issues/09-survey-relationship-edge-serving-options.md`

Date checked: 2026-09-19 (all URLs fetched/searched this date unless noted).

Read-only research. No vendor account was provisioned, no data was loaded
anywhere, and no repo files besides this one were touched. This does not
reopen or amend ADR 0009 (`docs/adr/0009-mongo-decision-projection.md`,
accepted: v2 agents read a **Mongo Decision Projection** on Atlas Free/M0
for the tabular As-Of Decision Features). Scope, per the ticket: this
survey is about the **relationship-edge half** of the v2 layer only
(`IS_INSIDER`, `EMPLOYED_BY` — subject-predicate-object edges), using the
same hard filter that decided MongoDB — free-tier and publicly
network-reachable, no ongoing warehouse cost. This does not decide which
option wins; that is explicitly a later grilling ticket's job.

**ADR 0001 scope check (done, not taken on faith per the ticket's own
instruction):** ADR 0001 (`docs/adr/0001-agent-decision-surface-first.md`)
was read in full. It does not mention Neo4j anywhere, including in its
"Considered options (rejected)" list — the ticket's citation of ADR 0001
for a "no external Neo4j" ruling is **not where that ruling actually
lives**. The real ruling is CLAUDE.md's "Graph storage" note (traced to
the `neo4j-snowflake` workstream, v1.3, completed 2026-06-12): the
platform's own **MDM** graph moved from an external Neo4j/AuraDB
relationship into the Neo4j Graph Analytics **Native App running inside
Snowflake** — "There is no separate Neo4j database, no `NEO4J_URI`/
`NEO4J_PASSWORD` secret, and no external Bolt connection." That ruling is
scoped to MDM's own internal graph storage/sync architecture. It says
nothing about, and does not forbid, a **separate, public, v2 agent-facing**
property-graph service such as Neo4j AuraDB Free evaluated below — those
are two unrelated "Neo4j" questions that happen to share a vendor name.
ADR 0009 (the actual v2 serving ADR) locks Mongo/Atlas for the tabular
features and says nothing about the edge layer one way or the other.

---

## Summary of the load-bearing facts

- **Question 1 (SPARQL/RDF) was already researched** in
  `.scratch/agent-contract-query-interface-options/research/01-free-public-sparql-hosting.md`
  (2026-09-19). Summarized in §1 below rather than re-run. Headline: no
  vendor in the named list offers a permanently-free, bring-your-own-data,
  publicly-reachable SPARQL endpoint with Atlas-M0-level documented limits;
  the closest analog found, **TriplyDB** ("first million triples free"),
  could not be confirmed against a primary pricing page — and in this
  session's one permitted follow-up check, the reason became clearer:
  Triply's own legacy pricing domain (`legacy.triply.cc`) no longer
  resolves (DNS failure), and no working pricing page was found anywhere
  on the current `triplydb.com` / `docs.triply.cc` domains either. The
  claim remains **unconfirmed**, now with an added signal that the
  original source describing it may itself be stale.
- **Hosted property-graph DBs: none of the four named vendors is a
  confirmed permanent-free, publicly-reachable, bring-your-own-data
  managed instance without an expiry/deletion risk.** Neo4j AuraDB Free is
  the closest — genuinely free forever, publicly reachable by default
  (`neo4j+s://...databases.neo4j.io`, TLS, credential auth, no IP
  allowlisting available at this tier) — but an AuraDB Free instance is
  **auto-deleted, unrecoverable, after 30 days of inactivity**, directly
  quoted from Neo4j's own FAQ ("Free-tier databases without activity for
  30 days are deleted"). Secondary sources (support-article search
  summaries, not independently fetched) describe a two-step version of
  this — paused after 3 days with no write queries, then deleted after 30
  days paused (33+ days total) — which is not the same timeline as the
  FAQ's direct single-trigger wording; this survey did not resolve which
  is accurate, and flags the 3-day pause figure as secondary-sourced only.
  Either way, the confirmed, load-bearing fact is that a Free AuraDB
  instance eventually **auto-deletes with no recovery**, a harder failure
  mode than Atlas M0, which pauses after 30 days idle but is documented as
  resumable with no stated auto-delete. ArangoDB's managed cloud (renamed at least twice — Oasis →
  ArangoGraph → now "AMP," Arango Managed Platform, under the rebranded
  `arango.ai` domain) has **no free tier found**; its only free offering is
  a self-hosted-only Community Edition. TigerGraph's only **permanent**
  free option is likewise self-hosted (TigerGraph Community, up to 300 GB,
  no expiry); its cloud offerings (classic Cloud and the newer Savanna
  platform) are credit/trial-based, not permanent.
- **Amazon Neptune is not re-researched here** — the prior SPARQL research
  already established, from `aws.amazon.com/neptune/pricing` (checked
  2026-09-19), that Neptune's "free tier" is a 30-day trial that reverts to
  on-demand billing (~$0.348/hr smallest instance, ~$254/month). Neptune's
  property-graph query surface (openCypher, Gremlin, and Neptune Analytics)
  runs on the same provisioned/serverless billing, so it fails this
  survey's filter identically under either query-language framing.
- **GraphQL-over-HTTP: Hasura Cloud has a real, currently-live, permanent
  free tier** (1 GB data passthrough/month, no time limit, removed the
  single-region restriction on the Free plan) — but Hasura is a GraphQL
  *layer* over an existing database, not storage itself, so it still needs
  a free-tier Postgres backing it (e.g. Neon or Supabase, both of which
  pause compute on inactivity but — unlike AuraDB Free — do not delete
  data). No head-to-head LLM benchmark comparing GraphQL query generation
  against SPARQL/SQL/Cypher/MQL under identical conditions (the SM3 study's
  methodology) was found; standalone GraphQL-only benchmarks report
  zero-shot accuracy under 15% and few-shot/in-context accuracy in the
  31–50% range depending on schema complexity — in the same rough band as
  SPARQL's few-shot number from SM3, not directly comparable.
- **Plain REST/JSON over free static hosting has real, permanently-free,
  publicly-reachable candidates on both AWS and Cloudflare.** Amazon
  CloudFront's wording is confirmed as "Always Free" (no 12-month
  expiration) directly from AWS's own dedicated free-tier page, though the
  exact numeric allowance is unsettled — that same page states 1 TB/10M
  requests per month, while AWS's own CloudFront pricing page, fetched the
  same day, shows a "$0/month" row at 100 GB/1M requests, and this survey
  did not resolve which is current (see §4). Amazon S3's 5 GB storage /
  20,000 GET / 2,000 PUT is
  consistently reported across AWS's own free-tier categorization and
  multiple secondary sources as belonging to the same "Always Free" bucket
  (distinct from the 12-months-new-account trial), though no single primary
  page fetch in this pass could be made to spell out that exact table row
  verbatim — flagged accordingly. **Cloudflare R2** (10 GB-month storage,
  1M Class A / 10M Class B ops per month, zero egress, no stated
  expiration) and **Cloudflare Pages** (unlimited bandwidth/egress for
  static assets, free, no expiration) are both confirmed real
  permanently-free alternatives that clear the same bar without AWS's
  July-2025 account-structure caveat. This option only fits point lookups
  by known key (e.g., one JSON file per CIK), not open-ended graph
  traversal — flagged, not resolved, per the ticket's instruction. A CDN in
  front (CloudFront or Cloudflare's own edge cache) also introduces a
  concrete fail-closed hazard: a stale cached edge document can keep being
  served to an agent after the origin object has already flipped to
  `not_ready`, unless cache TTL/invalidation is handled explicitly.
- **One structural fact carried through every candidate, mechanism-agnostic
  per the ticket's scope note:** every option surveyed *can* carry a
  generation/watermark stamp and support in-place fail-closed hiding as a
  data-modeling choice (a node/edge property in Neo4j/ArangoDB/TigerGraph;
  a GraphQL resolver field; a JSON field in a static document) — none of
  the four families is structurally incapable of it the way, e.g., a
  16 MiB single-document cap structurally blocked one Mongo shape in the
  predecessor research. The static-hosting option is the one exception
  worth flagging: CDN caching means "fail closed" requires either short
  TTLs, cache invalidation on publish, or a client-side READY check against
  an uncached endpoint — a real operational difference from the other
  three families, where the query engine itself always returns current
  server state.

---

## 1. SPARQL/RDF (summarized, not re-researched)

Full detail: `.scratch/agent-contract-query-interface-options/research/01-free-public-sparql-hosting.md`
(2026-09-19). Key points relevant to this survey:

- No vendor in the task's named list (Stardog, Ontotext GraphDB, Amazon
  Neptune) offers a confirmed permanently-free, bring-your-own-data,
  publicly-reachable SPARQL 1.1 endpoint documented to Atlas-M0 depth.
  Stardog's only free option is a **read-only shared demo** (cannot load
  your own data); GraphDB Free is self-host-only; Neptune is a 30-day
  trial.
- The closest match found, **TriplyDB** ("hosts your first million open
  data triples for free," per multiple secondary sources), was
  **unconfirmed** against a primary pricing page in that research pass.
  This survey's one permitted follow-up (see below) did not resolve it
  further — it surfaced an additional reason for low confidence.
- **Self-hosting** (Apache Jena Fuseki or Oxigraph) on **Oracle Cloud
  "Always Free"** (ARM Ampere A1, up to 4 OCPU/24 GB RAM, no time limit) is
  the one genuinely free-forever, always-on compute route found for a
  SPARQL endpoint — fully self-managed (TLS, auth, patching are your
  problem), not a turnkey hosted product.
- **Wikibase Cloud** is free and includes a built-in SPARQL query service,
  but is shaped for Wikibase's own item/statement data model, not
  bring-your-own Turtle/N-Triples.
- RDF triples are a natural fit for the edge shape (`IS_INSIDER`,
  `EMPLOYED_BY` as binary subject-predicate-object statements) but an
  awkward fit for watermark/period-scoped numeric facts, which need an
  n-ary-relation pattern (reification, intermediate resource, singleton
  properties, or RDF-star) per W3C's own guidance — not relevant to this
  ticket's edge-only scope, but noted since it's the reason the prior
  research scoped SPARQL to the edge half in the first place.
- **SM3-Text-to-Query** (NeurIPS 2024) is the one rigorous, primary-sourced,
  same-methodology LLM benchmark across four query languages on identical
  data: SQL 47.05%, Cypher 34.45%, MQL (MongoDB) 21.55%, SPARQL 3.3%
  zero-shot (SPARQL rising to ~30% with five-shot prompting). No GraphQL
  arm exists in that study (see §3 below for GraphQL's own, differently-run
  benchmarks).

### This survey's one follow-up: TriplyDB direct check

Per the ticket's explicit invitation, one direct primary-source check was
attempted in this session:

- `https://legacy.triply.cc/subscriptions/` — **DNS failure**
  (`getaddrinfo ENOTFOUND legacy.triply.cc`), i.e. the domain the prior
  research's own citation pointed at no longer resolves at all.
- `https://triplydb.com/` — loads, has a "Create a free account" call to
  action (implying *some* free tier exists) but the fetched content did not
  surface a pricing page or state the "first million triples" limit.
- `https://docs.triply.cc/triply-db-getting-started/` — product
  documentation only; no pricing/limits content, no link to a pricing page
  found in the fetched content.

**Net: still unconfirmed**, and now with one additional fact — the
originally-cited pricing domain is dead — that lowers rather than raises
confidence in the "first million triples free" claim without a working
primary source to check it against. This was the ticket's one invited
direct check ("flag the one unconfirmed lead ... if it's worth a direct
check"); it was made once and did not resolve the claim, so no further
attempts were made in this pass.

---

## 2. Hosted property-graph DBs (Gremlin/Cypher/GSQL)

| Vendor / product | Permanently free? | What the free tier actually is | Public reachability | Idle/pause/delete behavior | Source |
| --- | --- | --- | --- | --- | --- |
| **Neo4j AuraDB Free** | **Yes, the instance itself never expires on its own** — but see delete policy | Single database, **up to 200,000 nodes and 400,000 relationships** (direct quote: "AuraDB Free provides a single database supporting up to 200k nodes and 400k relationships") | Public by default — `neo4j+s://<id>.databases.neo4j.io`, TLS, SCRAM-style credential auth; **IP filtering/allowlisting is documented as available only on Virtual Dedicated Cloud and Business Critical tiers, not Free** | **Confirmed by direct FAQ quote: "Free-tier databases without activity for 30 days are deleted"** — a single-trigger, 30-day-inactivity-to-delete timeline. Secondary sources (search-result summaries over Neo4j support articles, not independently fetched) instead describe a two-step version — paused after 3 days with no write queries, deleted after a further 30 days paused (33+ days total) — which does not match the FAQ's own wording; the discrepancy is unresolved in this pass, and the 3-day figure is flagged as secondary-sourced only. Either timeline ends the same way: unrecoverable deletion | [neo4j.com/cloud/platform/aura-graph-database/faq](https://neo4j.com/cloud/platform/aura-graph-database/faq/) (fetched directly 2026-09-19, quote above); two-step timeline from search-result summaries over [support.neo4j.com — Why is my AuraDB Free Instance Paused](https://support.neo4j.com/s/article/4406830696083-Why-is-my-AuraDB-Free-Instance-Paused) and [support.neo4j.com — Aura Instance Access Issues](https://support.neo4j.com/s/article/17480821630355--Aura-Instance-Access-Issues-Understanding-Pausing-Resuming-and-Auto-Delete-Policy) (checked via search 2026-09-19, not directly fetched — both returned CSS-error pages on direct fetch attempts); IP filtering scope from [neo4j.com/docs/aura/security/ip-filtering](https://neo4j.com/docs/aura/security/ip-filtering/) (checked 2026-09-19) |
| **ArangoDB managed cloud** (product renamed at least twice: **Oasis → ArangoGraph Insights Platform → now "AMP" / Arango Managed Platform**, under the rebranded `arango.ai` domain — company itself now brands as "Arango" / "Arango Contextual Data Platform") | **No free tier found for the managed cloud product** | The managed platform's own pricing page offers only "Request Pricing" / "Talk to an Expert" — no self-serve free instance found. The only free option located anywhere on the current site is **"Community Edition: open source, free for evaluation and non-commercial use"** — explicitly self-hosted, not the managed cloud | n/a (no free managed offering found) | n/a | [arango.ai](https://arango.ai/) and [arango.ai/pricing](https://arango.ai/pricing/) (fetched 2026-09-19); rename chain corroborated by [github.com/arangodb-managed/oasisctl](https://github.com/arangodb-managed/oasisctl) ("formerly called Oasis") and [docs.arangodb.com/3.11/arangograph](https://docs.arangodb.com/3.11/arangograph/) (search results, checked 2026-09-19) |
| **TigerGraph** (cloud platform now called **Savanna**; the older product is referred to in docs as "TigerGraph Cloud") | **Only the self-hosted edition is permanent-free; no cloud tier is** | **TigerGraph Community** (self-hosted): free, no stated expiry, up to 300 GB combined graph+vector storage, single-server, includes GSQL/Cypher/GQL support. **TigerGraph Cloud** (classic): a $25 credit granted to new accounts, valid 30 days. **Savanna**: free credits valid for one year (extendable via onboarding tasks), but Savanna's own pricing docs page shows only paid per-hour/per-GB rates ($1/hr smallest compute size, $0.025–0.044/GB-month storage) with no permanent free row | Cloud/Savanna: standard public cloud reachability (paid, provisioned). Community: self-hosted, your own network responsibility | Cloud/Savanna: credits expire (30 days or 1 year); no evidence of an auto-delete-on-pause policy comparable to AuraDB's, because these are trial-credit models rather than a standing free instance | [tigergraph.com/pricing](https://www.tigergraph.com/pricing/) (fetched 2026-09-19, Community Edition details); [tigergraph.com/docs/savanna/main/overview/pricing](https://www.tigergraph.com/docs/savanna/main/overview/pricing) (fetched 2026-09-19, paid-rate table); credit terms from search results over [docs-beta.tigergraph.com/tigergraph-cloud/tigergraph-cloud-faqs](https://docs-beta.tigergraph.com/tigergraph-cloud/tigergraph-cloud-faqs) and [tigergraph.com/savanna-faq](https://www.tigergraph.com/savanna-faq/) (checked 2026-09-19) |
| **Amazon Neptune** | **No** — not re-researched here; see `.scratch/agent-contract-query-interface-options/research/01-free-public-sparql-hosting.md` §1, confirmed from `aws.amazon.com/neptune/pricing` (checked 2026-09-19): 30-day trial only, reverts to on-demand billing (~$0.348/hr smallest instance ≈ $254/month) or Neptune Serverless consumption billing. Neptune Analytics / openCypher / Gremlin run on the same billing surface — the property-graph framing does not change the answer. | | | | (see cited prior file) |

### Net on question 2

No hosted property-graph vendor among the four named is a confirmed
permanent-free, bring-your-own-data, publicly-reachable managed instance
free of an expiry or deletion risk, to the same documented-limits standard
as Atlas M0. Neo4j AuraDB Free comes closest — genuinely free forever as a
*product offering*, publicly reachable with TLS + credentials by default,
with a real, primary-sourced 200k-node/400k-relationship capacity ceiling —
but carries a real, primary-confirmed **data-loss** risk (30 days paused →
permanent delete) that Atlas M0's documented idle-pause behavior does not
share (M0 is described as resumable, with no stated auto-delete).
ArangoDB's rebranded managed platform has no free tier at all as of this
check. TigerGraph's only permanent-free option is self-hosted, in the same
category as Fuseki/Oxigraph in the SPARQL research (free *software*, your
own hosting problem) rather than a turnkey managed free service.

---

## 3. GraphQL-over-HTTP on a free-forever host

| Option | Permanently free? | What it actually is | Public reachability | Idle/pause behavior | Source |
| --- | --- | --- | --- | --- | --- |
| **Hasura Cloud (Free plan)** | **Yes** — no stated expiration on the Free plan itself | GraphQL API layer generated over a connected Postgres data source; **1 GB data passthrough per month**; single-region restriction on Free has been removed (can deploy to any available region) | Public HTTPS GraphQL endpoint, standard Hasura Cloud networking | **Hibernates after ~90 days of total inactivity** (first notice at 60 days, reminder at 75, hibernation at ~90) — metadata and project config preserved; API calls unavailable until manually reactivated; **not a data-delete event**, unlike AuraDB Free's 30-day auto-delete | Free-tier limits/region change from search-result summaries over [hasura.io/docs/2.0/hasura-cloud/plans](https://hasura.io/docs/2.0/hasura-cloud/plans/) and the Hasura pricing-updates blog post (checked 2026-09-19); hibernation timeline from [hasura.io/docs/2.0/hasura-cloud/projects/hibernation](https://hasura.io/docs/2.0/hasura-cloud/projects/hibernation/) (checked 2026-09-19) |
| **Hasura's required backing database** | Hasura itself is not storage — needs a Postgres data source | Candidates: **Neon Free** (100 projects, 0.5 GB storage/project, 100 CU-hours/month, compute **auto-suspends after 5 minutes idle but the project is not paused/deleted** — "scale to zero," not hibernation) or **Supabase Free** (project **pauses after 7 days of low activity**; first request after pause takes 10–30s to cold-start; restorable from the dashboard, not auto-deleted) | Both publicly reachable Postgres-over-TLS endpoints | Neon: per-compute auto-suspend (seconds-scale, transparent). Supabase: 7-day inactivity pause (requires a manual/automated restore or keep-alive ping) | [neon.com/faqs/free-plan-limits-and-quotas](https://neon.com/faqs/free-plan-limits-and-quotas) and [neon.com/docs/introduction/plans](https://neon.com/docs/introduction/plans) (search results, checked 2026-09-19); [supabase.com/docs/guides/platform/free-project-pausing](https://supabase.com/docs/guides/platform/free-project-pausing) (search results, checked 2026-09-19) |
| **Other serverless-function-over-free-store GraphQL shapes** (e.g. a Lambda/Cloudflare Worker resolver over free storage) | Not surveyed as a distinct named product — this is a build-it-yourself pattern, not a vendor offering; the underlying free-forever storage/compute pieces are the same ones evaluated in §4 below (S3/CloudFront, R2, Cloudflare Pages/Workers) | n/a | n/a | n/a | n/a |

### GraphQL's query-shape fit for an LLM agent (question 3's second half)

No benchmark was found that runs GraphQL head-to-head against SPARQL/SQL/
Cypher/MQL on identical data under the SM3 methodology (same dataset,
same models, same accuracy metric) — stated plainly, per the ticket's own
instruction for exactly this situation, rather than manufacturing a
comparison. What was found, from GraphQL-only text-to-query studies:

- A large training/benchmarking dataset study (ACL Anthology, EMNLP 2024
  industry track) reports LLMs "struggle with GraphQL query generation due
  to limited exposure to publicly available GraphQL schemas."
- A synthetic-schema NL2GraphQL benchmark (20 real-world schemas, 1,845
  validated instances) reports **zero-shot accuracy under 15%** for most
  models tested, rising to **31–48%** across eight contemporary LLMs with
  in-context examples, and up to **~50%** for the best model with one
  in-context example.

These numbers were produced by a different benchmark family (different
dataset, different models, different scoring) than SM3's SQL/Cypher/MQL/
SPARQL comparison, so they are **not directly comparable figures** — only
directionally informative that GraphQL, like SPARQL, sits well below SQL's
same-study 47% zero-shot and improves substantially with few-shot
examples, echoing the SM3 authors' own explanation (training-data
frequency) for SPARQL's low score. No source was found stating GraphQL
generation accuracy specifically *relative to* SPARQL under one shared
protocol.

### Net on question 3

Hasura Cloud's Free plan is a real, currently-live, permanently-free
managed GraphQL host — the strongest "real permanently-free public option"
found for GraphQL-over-HTTP — but it is a query layer, not storage, so a
working deployment composes it with a free Postgres tier that has its own
pause behavior (Neon's transparent scale-to-zero is milder than Supabase's
7-day pause, both milder than AuraDB Free's 30-day delete). No
evidence — confirmed absent, not merely unsearched — answers whether
GraphQL's query shape suits an LLM agent better or worse than SPARQL
specifically; the two are measured in different studies with different
scoring, and both trail SQL by a similar-shaped, training-data-frequency
explanation in their respective source papers.

---

## 4. Plain REST/JSON over free static/object hosting

| Option | Permanently free? | Limits | Public reachability | Fail-closed/staleness consideration | Source |
| --- | --- | --- | --- | --- | --- |
| **Amazon S3** (static object storage) | **Reported as "Always Free" (not the 12-month-only trial bucket)**, but see confidence note below | **5 GB Standard storage, 20,000 GET requests, 2,000 PUT requests per month** | Public via bucket policy / static website hosting; standard HTTPS | No CDN cache in front by default — a direct S3 GET reflects the current object immediately once written | `aws.amazon.com/free/storage/s3/` fetched 2026-09-19 (fetch did not itself surface the numeric table); numbers and "Always Free" categorization corroborated by multiple secondary sources (search results, checked 2026-09-19) — see confidence note |
| **Amazon CloudFront** (CDN in front of S3 or any origin) | **Confirmed "Always Free," no expiration** — direct fetch of AWS's own dedicated free-tier networking page states this explicitly | **Conflicting numbers across two AWS pages fetched the same day — not resolved in this pass.** `aws.amazon.com/free/networking/` (the dedicated free-tier page): "1 TB of Data Transfer Out," "10 Million HTTP or HTTPS Requests," "2 million CloudFront Function invocations," stated as "always free." `aws.amazon.com/cloudfront/pricing/` (the product pricing page): a "$0/month" row showing "100GB" data transfer and "1M" requests, "No overage charges." Both fetched 2026-09-19; neither fetch stated why they differ. One plausible read (not confirmed): the smaller 100 GB/1M figure is the post-July-2025 "Free plan" cap, and the 1 TB/10M figure is the older, persistent "Always Free" allowance — the same pre/post-restructuring fork documented for S3 above — but this was not independently verified for CloudFront the way it was for S3 | Public HTTPS edge network, global | **Concrete fail-closed hazard**: a cached edge document can continue being served to an agent for as long as its TTL, even after the origin object has already flipped to a `not_ready`/hidden state — requires explicit TTL tuning or cache invalidation on publish to preserve the fail-closed property this survey's scope requires | `aws.amazon.com/free/networking/` and `aws.amazon.com/cloudfront/pricing/`, both fetched directly 2026-09-19 |
| **Cloudflare R2** (S3-compatible object storage) | **Yes, confirmed — no stated time limit** | **10 GB-month storage/month, 1 million Class A operations/month, 10 million Class B operations/month, egress free** ("The free tier only applies to Standard storage, not Infrequent Access") | Public via bucket policy or a custom domain; HTTPS | Same as S3 — a direct R2 read is not cached unless deliberately fronted by Cloudflare's CDN/cache rules | `developers.cloudflare.com/r2/pricing` fetched directly 2026-09-19 |
| **Cloudflare Pages** (static site/API hosting) | **Yes, confirmed — no stated expiration, commercial use allowed** | **Unlimited bandwidth for static asset requests** (zero egress fees); 500 builds/month; Pages *Functions* (dynamic) capped at 100,000 requests/day on the free plan, shared with Workers free-plan quota | Public HTTPS with free SSL, unlimited custom domains | Same CDN-caching fail-closed hazard as CloudFront, since Cloudflare's edge network caches static assets by default | Search-result summaries over `developers.cloudflare.com/pages/functions/pricing` (checked 2026-09-19) — not independently re-fetched from the primary page in this pass; flagged as **secondary-sourced, not primary-confirmed**, unlike R2 above |
| **GitHub Pages** | Free (no separate pricing tier — bundled with a GitHub account) | **Soft** bandwidth limit of ~100 GB/month (not hard-metered; GitHub states it may throttle or warn on sustained high usage rather than bill), published site size capped at 1 GB | Public HTTPS, `github.io` subdomain or custom domain | Backed by a CDN (Fastly); same class of caching hazard as CloudFront/Cloudflare Pages | Search-result summaries over `docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits` (checked 2026-09-19) — not independently re-fetched from the primary docs page in this pass; flagged **secondary-sourced** |

### Confidence note — S3's "Always Free" categorization

AWS restructured its Free Tier program on **July 15, 2025**: new accounts
now get a 6-month "Free plan" with up to $200 in credits, replacing the
prior 12-months-free structure for *new* signups. Multiple secondary
sources, plus the framing of AWS's own dedicated `aws.amazon.com/free/`
subpages (`/free/storage/s3/`, `/free/networking/`), consistently describe
S3's 5 GB / 20,000-GET / 2,000-PUT allowance and CloudFront's 1 TB / 10M
allowance as both belonging to a separate, persistent **"Always Free"**
category (one of "more than thirty always-free services") that exists
independently of the July-2025 restructuring and applies to both
pre-existing and newly-created accounts. CloudFront's page states this in
so many words on direct fetch ("always free"). S3's equivalent page did not
yield the same explicit sentence on direct fetch in this pass (the page's
rendered/JS-driven table was not captured by the fetch tool used here) —
so the S3 "Always Free, indefinite" claim is **corroborated by consistent
secondary sourcing and AWS's own free-tier page structure, but not
independently quoted verbatim from a primary page** in this research pass.
Flagged as **confirmed via structure, unconfirmed via direct quote**.

### The point-lookup vs. traversal tradeoff (flagged, not resolved, per the ticket)

Every option in this section serves **pre-materialized documents fetched
by a known key** (e.g., `GET /issuers/0000320193/edges.json`) — there is no
query language, no filtering, no multi-hop traversal server-side. An agent
that already knows the CIK it cares about and wants "this issuer's
insiders and employer" gets a fast, cheap, fully-cacheable answer. An
agent that wants "find all issuers where person X is an insider" (a
reverse/multi-hop lookup) gets nothing from this shape unless a second,
separately-materialized index document is published for that access
pattern too — the tradeoff is real and structural, not a tuning problem,
and resolving it is explicitly out of scope for this survey.

### Net on question 4

CloudFront's "always free" wording is the one claim in this whole survey
confirmed by a direct-quote primary-source fetch stating "always free"
outright — but the exact numeric allowance behind that wording is not
settled: two AWS pages fetched the same day give 1 TB/10M requests versus
100 GB/1M requests (see the CloudFront table row above), and this survey
did not resolve which applies today. S3, R2, and Cloudflare Pages/GitHub
Pages all
clear the free-tier + public-reachability filter on the weight of
consistent sourcing, with R2 additionally confirmed by direct primary-page
fetch. All of them share the same structural limitation (point lookup by
key, not open-ended graph query) and the same class of CDN-caching
fail-closed hazard where a CDN sits in front.

---

## 5. Options that fail the filter — one line each

(Vendors already covered in §§1–4's own tables are not repeated here; this
section is for anything considered and ruled out before it earned a table
row above.)

- **Databricks Free Edition** — non-commercial only, per the `mongodb-v2-agent-interface` map's own prior note; not evaluated further.
- **Snowflake trial** — time-limited trial, not a permanent free tier, per the same map note; already ruled out for v1/v2 Mongo work and equally inapplicable here.
- **Google Cloud / Azure managed RDF-SPARQL products** — no first-party offering found at all (see prior SPARQL research, corroborated again in this pass via the Cosmos DB/Gremlin and Spanner Graph findings, which are property-graph not RDF).
- **Azure Cosmos DB for Apache Gremlin** — fully-managed property graph, but no confirmed permanent-free tier was located in this pass and it was not part of the ticket's named list; not surveyed to table depth, noted only because the prior SPARQL research surfaced it as a Google/Azure "near miss."
- **Stardog Cloud / GraphDB Managed Service** — sales-quote-only paid enterprise products, no free tier (already established in the prior SPARQL research; reconfirmed as out of scope for this pass).
- **Fly.io** — free compute allowance removed for new accounts October 2024 (prior SPARQL research finding, applies identically here as a hosting substrate for any self-hosted graph DB).
- **Render.com free web service** — no persistent disk on free tier, 15-minute idle spindown; ruled out as a stateful-database host for the same reason the prior SPARQL research ruled it out for Fuseki.

---

## Sources

Official/primary (fetched or quoted directly, checked 2026-09-19 unless noted):

- https://neo4j.com/cloud/platform/aura-graph-database/faq/
- https://neo4j.com/docs/aura/security/ip-filtering/
- https://arango.ai/
- https://arango.ai/pricing/
- https://www.tigergraph.com/pricing/
- https://www.tigergraph.com/docs/savanna/main/overview/pricing
- https://developers.cloudflare.com/r2/pricing/
- https://aws.amazon.com/free/networking/
- https://aws.amazon.com/free/storage/s3/ (fetched; did not itself yield the numeric table)
- https://aws.amazon.com/s3/pricing/ (fetched; free-tier table not present in rendered content)
- https://legacy.triply.cc/subscriptions/ (DNS failure — domain does not resolve)
- https://triplydb.com/ (fetched; no pricing content surfaced)
- https://docs.triply.cc/triply-db-getting-started/ (fetched; no pricing content surfaced)
- https://arxiv.org/abs/2411.05521 (SM3-Text-to-Query — reused from prior research, not re-fetched this pass)

Secondary (search-result-derived; flagged inline above where a table cell relies on one, not a primary-page direct quote):

- https://support.neo4j.com/s/article/4406830696083-Why-is-my-AuraDB-Free-Instance-Paused
- https://support.neo4j.com/s/article/17480821630355--Aura-Instance-Access-Issues-Understanding-Pausing-Resuming-and-Auto-Delete-Policy
- https://github.com/arangodb-managed/oasisctl
- https://docs.arangodb.com/3.11/arangograph/
- https://docs-beta.tigergraph.com/tigergraph-cloud/tigergraph-cloud-faqs
- https://www.tigergraph.com/savanna-faq/
- https://hasura.io/docs/2.0/hasura-cloud/plans/
- https://hasura.io/docs/2.0/hasura-cloud/projects/hibernation/
- https://neon.com/faqs/free-plan-limits-and-quotas
- https://neon.com/docs/introduction/plans
- https://supabase.com/docs/guides/platform/free-project-pausing
- https://developers.cloudflare.com/pages/functions/pricing/
- https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
- https://aclanthology.org/2024.emnlp-industry.117/ (GraphQL query generation benchmark, EMNLP 2024 industry track)
- Synthetic Data Generation for Schema-Aware Query Interfaces: Benchmarking NL2GraphQL Systems (ACM, DL reference found via search; not independently opened as a PDF in this pass)
- AWS Free Tier July-2025 restructuring: multiple third-party summaries (freetier.co, infratally.com, techbytes.app, dev.to) converging on the same "Always Free unaffected, 12-month-trial replaced by 6-month Free Plan for new accounts" account — no single primary AWS "what changed" announcement page was fetched directly in this pass

In-repo:

- `.scratch/mongodb-v2-agent-interface/issues/09-survey-relationship-edge-serving-options.md`
- `.scratch/mongodb-v2-agent-interface/map.md`
- `.scratch/mongodb-v2-agent-interface/research/01-atlas-free-vs-bundle-size.md`
- `.scratch/agent-contract-query-interface-options/research/01-free-public-sparql-hosting.md`
- `docs/adr/0001-agent-decision-surface-first.md`
- `docs/adr/0009-mongo-decision-projection.md`
- CLAUDE.md "Graph storage" note (the actual location of the "no external Neo4j" ruling, scoped to MDM's own graph, not this v2 survey)
