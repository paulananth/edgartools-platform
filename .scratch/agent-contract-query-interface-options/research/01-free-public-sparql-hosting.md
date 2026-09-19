# SPARQL/RDF triple-store endpoints as a v2 Agent Decision Surface option

Date checked: 2026-09-19 (all URLs fetched/searched this date unless noted).

Read-only research. No vendor account was provisioned, no data was loaded
into any SPARQL endpoint, and no repo files besides this one were touched.
This does not reopen or amend ADR 0009 (`docs/adr/0009-mongo-decision-projection.md`,
accepted: v2 agents read a **Mongo Decision Projection** on Atlas Free/M0).
It answers a standing research question about whether SPARQL/RDF could
serve as, or contribute to, that same v2 surface — findings only, no
recommendation.

**Referenced-but-missing prior file:** the task pointed at
`.scratch/agent-decision-v1-inputs/research/10-free-public-agentic-databases.md`
for framing/format. That path does **not exist** in this worktree. Checked:
`find` across the full repo and every local branch/worktree (zero hits);
`git log --all -- <path>` (empty — no commit ever touched it, in either
this worktree or the reflog); confirmed `.scratch/` is **tracked, not
gitignored** (`git check-ignore` on a sibling file that does exist,
`.../01-live-financial-factors-bind.md`, returns nothing, and that sibling
file has real git history — `e9e65aa9`), so an untracked/gitignored
`.scratch/` cannot explain the gap; and a direct file-path check against
every other local worktree's own `.scratch/` directory
(`edgartools-platform-clean-mdm`, `-clean-mdm-integration`,
`-sec-gleif-company`, `-grok-local-postgres`, and the two under
`-worktrees/`) — the file is absent from all of them too, so it is not
sitting uncommitted in a sibling checkout. The path was genuinely never
created, only referenced. It is
referenced by name from two other in-repo files that do exist —
`.scratch/mongodb-v2-agent-interface/research/01-atlas-free-vs-bundle-size.md`
(lines 13–15, 318–320, 370–373) and (by inference) the MongoDB v1 verdict
doc — which summarize its conclusion in passing: "M0 is the only
perpetually free public hostname of the three vendors [it compared]" and
"allowlist the agent IP or `0.0.0.0/0`." Beyond that one-line summary, this
file's original content, and which three vendors it compared, could not be
recovered. This research instead follows the closest available in-repo
format analogs — `01-atlas-free-vs-bundle-size.md` and
`.scratch/agent-decision-contract/research/10-json-mongodb-agentic-data-plane.md`
— for structure (cited-limits tables, verdict-style summary stated as
fact not recommendation, explicit confirmed/unconfirmed flags, Sources
list).

---

## Summary of the load-bearing facts

- **No vendor found — across both the task's named list and a broader
  sweep for linked-data-specific hosting services — offers a permanently-
  free, publicly-reachable, bring-your-own-data hosted SPARQL 1.1 endpoint
  that is a full, confirmed analog of Atlas M0** (i.e., with the same level
  of documented limits: storage cap, ops/s, TLS/auth model, idle behavior,
  all from a primary pricing/limits page). Every commercial triple-store
  vendor checked in the named list (Stardog, Ontotext GraphDB, Amazon
  Neptune) either has no perpetual free hosted tier at all, or its only
  free hosted offering is a **read-only shared demo** you cannot load your
  own data into (Stardog Express). The broader sweep surfaced one **real,
  currently-operating candidate with the same shape as the named-list
  gap** — **TriplyDB**, which multiple secondary sources describe as
  hosting "the first million open data triples for free" with a public
  SPARQL endpoint — but this research could not independently confirm that
  claim against a primary TriplyDB pricing page in the time available (see
  §1, "Additional vendors found via a broader sweep," for the full caveat
  and the other near-misses found: AllegroGraph Cloud, QLever, Dydra,
  Fluree, and Oracle Autonomous Database's Always Free RDF Semantic Graph
  feature).
- **Amazon Neptune's "free tier" is a 30-day trial, not a permanent free
  tier** — it expires and reverts to on-demand billing (~$0.348/hr smallest
  instance, ~$254/month) or Neptune Serverless consumption billing.
- **Self-hosting Apache Jena Fuseki or Oxigraph is the only route to a
  genuinely free-forever, publicly-reachable SPARQL endpoint found** — but
  it requires a perpetually-free *compute* tier, not a SPARQL-specific
  vendor product. Of the compute options checked, Fly.io no longer has one
  (killed for new accounts Oct 2024) and Render's free web-service tier has
  no persistent disk and spins down after 15 minutes idle; **Oracle Cloud's
  "Always Free" tier (ARM Ampere A1, up to 4 OCPU/24 GB RAM, no time
  limit)** is the one perpetually-free, always-on compute option found that
  could carry a self-managed Fuseki/Oxigraph process — but that is
  fully self-managed infrastructure (you own TLS, auth, patching, uptime),
  not a turnkey hosted service comparable to Atlas M0.
- **Wikibase Cloud (wikibase.cloud) is free and includes a built-in SPARQL
  query service**, but it is shaped for Wikibase's wiki item/statement data
  model, not a generic triple store you load arbitrary Turtle/N-Triples
  into directly — using it would mean re-modeling the Decision Graph Bundle
  as Wikibase items/statements, not loading it as-is.
- **The one rigorous, primary-sourced LLM benchmark found (SM3-Text-to-Query,
  NeurIPS 2024) shows SPARQL as the weakest of four query languages for
  zero-shot LLM generation — 3.3% execution accuracy, versus 47.05% for SQL,
  34.45% for Cypher, and 21.55% for MongoDB Query Language (MQL)** — with
  the benchmark's own authors attributing the gap primarily to SPARQL's
  much lower representation in LLM pretraining data (Stack Overflow: SQL
  673K posts vs. SPARQL 6K posts), not an inherent property of the
  language. Five-shot prompting raised SPARQL accuracy to ~30% in the same
  study. A separate, differently-shaped study (arxiv 2311.07509, see §3)
  found a **38-point** answer-accuracy gain from adding a knowledge-graph/
  ontology layer versus querying SQL directly — a related but distinct
  claim, not a query-syntax-generation accuracy number; see §3 for why the
  two should not be conflated.
- **RDF triples fit relationship edges (`IS_INSIDER`, `EMPLOYED_BY`)
  naturally** — that is the textbook subject-predicate-object case — **but
  the As-Of Decision Features (tabular, watermark-dated, numeric) do not
  map as cleanly**: attaching point-in-time/watermark provenance to a
  single numeric fact requires an RDF n-ary-relation pattern (reification,
  an intermediate resource, singleton properties, or RDF-star), not a bare
  triple, per W3C's own guidance on the problem.

---

## 1. Free-tier, publicly-reachable SPARQL endpoint hosting

### Vendor-hosted SPARQL-as-a-service

| Vendor / product | Permanently free? | What the free tier actually is | Public network reachability | Idle/cold-start behavior | Source |
| --- | --- | --- | --- | --- | --- |
| **Stardog Express** ("Cloud Starter Kit") | Free, no stated expiration found | **Read-only** access to Stardog-provided sample datasets on a shared multi-tenant instance — you cannot load your own data | Publicly accessible per Stardog's own description ("publicly accessible shared resource") | Not documented; not applicable in the same sense since it's not your own dataset | [stardog.com/stardogexpress](https://www.stardog.com/stardogexpress/) (checked 2026-09-19) |
| **Stardog Free** (self-hosted license) | Free 1-year **renewable** license, but self-host only — no hosted cloud instance included | Lacks HA, caching, backups, LDAP integration, full connector set, per Stardog's own pricing page | You provide and secure the network path yourself (it's a downloaded server) | Your responsibility (self-hosted) | [stardog.com/pricing](https://www.stardog.com/pricing/) (checked 2026-09-19) |
| **Stardog Cloud** (managed, paid) | No — sales-call pricing only | n/a | n/a | n/a | Same page — FAQ states pricing requires "a few minutes with you on a call" |
| **Ontotext GraphDB Free** | Free (must request a license as of GraphDB 11.0+; no cost found) | **Self-host / on-premise only** in Ontotext's own feature-comparison table — not a hosted cloud instance; capped at **2 concurrent queries** | You provide and secure the network path yourself | Your responsibility (self-hosted) | [graphdb.ontotext.com/documentation/11.3/licensing.html](https://graphdb.ontotext.com/documentation/11.3/licensing.html) (checked 2026-09-19) |
| **GraphDB Managed Service / GraphDB Cloud** (Enterprise) | No | AWS Marketplace lists a "GraphDB Managed Evaluation (non-production)" at **$3,990/month**, 1-month contract; full Enterprise licensing is a separate vendor-billed relationship | Vendor-managed | Not documented (paid tier) | [ontotext.com/services/graphdb-managed-services](https://www.ontotext.com/services/graphdb-managed-services/); AWS Marketplace listing found via search (checked 2026-09-19; exact listing URL not independently re-verified beyond the search summary — flag as secondary-sourced) |
| **Amazon Neptune** | **No** — 30-day free **trial**, not a permanent tier | 750 hours of `db.t3.medium`/`db.t4g.medium`, 10M I/O requests, 1 GB storage + 1 GB backup, for 30 days from first cluster creation | Standard AWS networking (VPC; can be made publicly reachable with a public subnet/endpoint, same as any RDS/Neptune cluster — not a special "public SPARQL" product) | Trial simply expires after 30 days, not idle-based | [aws.amazon.com/neptune/pricing](https://aws.amazon.com/neptune/pricing/); [What's New: Neptune free trial, 2022](https://aws.amazon.com/about-aws/whats-new/2022/04/amazon-neptune-offers-free-trial/) (checked 2026-09-19) |
| **Google Cloud / Azure** managed SPARQL/RDF | **No offering found** | Repo-wide web search found no first-party managed SPARQL/RDF triple-store product from either Google Cloud or Azure as of this check. Third-party/community projects exist (e.g. ECARF, layering SPARQL over BigQuery) but are not vendor products. | n/a | n/a | Search only, no vendor page confirms a product exists (absence of evidence, checked 2026-09-19) — **flag as unconfirmed-negative**: a narrower, more targeted search of each vendor's own docs site was not performed in this pass |
| **Wikibase Cloud** (wikibase.cloud, Wikimedia Deutschland) | Appears free with no stated sunset for the free tier | Free-hosted Wikibase instance with a built-in Wikibase Query Service (SPARQL); allowlisted federation to Wikidata-style endpoints; REST API also enabled | Public hosting (it's a public wiki platform) | Not documented in sources found | [meta.wikimedia.org/wiki/Wikibase/Wikibase.cloud](https://meta.wikimedia.org/wiki/Wikibase/Wikibase.cloud); [mediawiki.org .../Hosting_policy](https://www.mediawiki.org/wiki/Wikibase/Wikibase.cloud/Hosting_policy) (checked 2026-09-19) — **could not confirm current capacity/rate limits or a formal SLA/pricing page** in the time available; treat "free, no sunset" as directionally true but unconfirmed against a canonical pricing page |
| **Virtuoso Open Source Edition (OSE)** | Free to **download**, self-host only | No managed free cloud tier found; an AWS Marketplace AMI listing exists but that is paid infrastructure, not a free vendor SaaS | Your responsibility (self-hosted) | Your responsibility (self-hosted) | [github.com/openlink/virtuoso-opensource](https://github.com/openlink/virtuoso-opensource); AWS Marketplace listing found via search (checked 2026-09-19) |

### Self-hosted-on-free-compute options (Jena Fuseki / Oxigraph)

Both Fuseki and Oxigraph are software you run yourself, not a hosted
product — the free-tier question shifts entirely to **which compute host is
perpetually free**:

| Compute host | Perpetually free? | Relevant constraint for a SPARQL server | Source |
| --- | --- | --- | --- |
| **Fly.io** | **No, not for new accounts.** Free allowances were removed for new signups in **October 2024**; new accounts get a 2-VM-hour / 7-day trial only, then pay from the first second. Legacy accounts created before that date may still be grandfathered. | n/a — ruled out for a new deployment | [fly.io/docs/about/discontinued-plans](https://fly.io/docs/about/discontinued-plans/); [saaspricepulse.com Fly.io Free Tier 2026](https://www.saaspricepulse.com/blog/flyio-free-tier-2026) (checked 2026-09-19) |
| **Render.com** (free web service) | Free, but with real limits | **No persistent disk on the free tier** — Fuseki's on-disk TDB2 dataset would not survive a restart without a paid disk add-on. Also **spins down after 15 minutes of no traffic**, ~30–60 second cold start on the next request. | [render.com/docs/faq](https://render.com/docs/faq); secondary summaries (checked 2026-09-19) |
| **Oracle Cloud "Always Free" tier** | **Yes — no time limit**, explicitly distinct from other providers' time-limited trials | ARM Ampere A1 instances: up to **4 OCPUs / 24 GB RAM** total, splittable across instances; also an AMD Micro shape (`VM.Standard.E2.1.Micro`, 1/8 OCPU / 1 GB RAM). Persistent, always-on VM (not serverless) — you install Docker/Fuseki/Oxigraph yourself and manage TLS, a public IP, firewall rules, and OS patching. | [medium.com/oracledevs — Run Always Free Docker Container on OCI](https://medium.com/oracledevs/run-always-free-docker-container-on-oracle-cloud-infrastructure-c88e36b65610); secondary 2026 setup guides (checked 2026-09-19) |

**Oxigraph** itself: a single-binary Rust SPARQL 1.1 server backed by
RocksDB, also usable as an embeddable library (`pyoxigraph` for Python, a
WASM `oxigraph` npm package for JS) with no external server process
required at all for an in-process use case. Positioned by its own docs/
GDB-Engines summary as aimed at **local / small-to-medium workloads
(millions to ~billions of triples)** — explicitly *not* the
trillion-triple, multi-replica, RBAC-heavy territory of Neptune/Stardog.
[github.com/oxigraph/oxigraph](https://github.com/oxigraph/oxigraph);
[gdb-engines.com/db/oxigraph](https://gdb-engines.com/db/oxigraph/)
(checked 2026-09-19).

### Additional vendors found via a broader sweep (not in the task's named list)

The task's list was explicitly "at minimum" — a broader search
(`"free hosted SPARQL endpoint" 2026`, and direct name searches) surfaced
these additional, currently-operating candidates. None was verified to the
same depth as the Atlas M0 table in the prior Mongo research (no primary
pricing/limits page was fetched for any of these); all are flagged
accordingly.

| Vendor / product | What was found | Free tier? | Confidence |
| --- | --- | --- | --- |
| **TriplyDB** (Triply/triplydb.com) | Hosted linked-data platform exposing SPARQL, GraphQL, Elasticsearch, Linked Data Fragments, and REST over uploaded RDF; supports free user accounts. Multiple independent search-result summaries state it "hosts your first million open data triples for free." | Reported free, capped at **1 million triples** (reported, not independently confirmed) | **Unconfirmed** — could not reach a primary pricing page (`legacy.triply.cc/subscriptions/` returned DNS failure on fetch; `triplydb.com` and `docs.triply.cc` pages fetched did not themselves state the limit). This is the one candidate that, *if* the reported limit is accurate, would be the closest like-for-like match to Atlas M0 found anywhere in this research — bring-your-own-data, publicly reachable, genuinely free, not a shared read-only demo. Needs primary-source confirmation before relying on it. |
| **AllegroGraph Cloud** (Franz Inc.) | "AllegroGraph Cloud is a fully featured Knowledge Graph platform provided as a hosted service," with a "Start Free — Simple Sign-up" call to action. | Sign-up flow exists; no limits, expiration, or trial-vs-permanent distinction found on the page fetched | **Unconfirmed** — the product page does not state whether "Start Free" is a permanent tier or a time-limited trial; not resolved in this pass |
| **QLever** | Open-source SPARQL engine (not a hosted vendor product) designed to query very large datasets (hundreds of billions of triples) on a single machine; free and open-source itself, with paid enterprise support available | Same category as Fuseki/Oxigraph — free *software*, hosting is your own problem | Confirmed as software; not a hosting vendor, so it doesn't change the hosting-vendor answer |
| **Dydra** | A commercial cloud RDF/SPARQL service (docs at docs.dydra.com) | Positioned as commercial/paid based on the sources found; no free-tier claim located | **Unconfirmed-negative** — did not find pricing details either way |
| **Fluree** | RDF 1.1/1.2 + SPARQL + JSON-LD + openCypher triplestore, notable for an immutable/blockchain-style ledger design | Open-source library (`fluree/db` on GitHub); hosting model not established in this pass | Same category as QLever — software, not a confirmed hosting vendor |
| **Oracle Autonomous Database "Always Free" + RDF Semantic Graph** | Oracle's Autonomous Database has a native RDF Semantic Graph feature (Graph Studio, a SPARQL query/insert/delete interpreter) that runs inside the same Always Free Autonomous Database tier already cited for Oracle's free compute. Oracle's own developer blog walks through deploying a public SPARQL endpoint (RDF Server on WebLogic or Tomcat) in front of it. | Free, no time limit, per Oracle's Always Free program (same program cited for the compute-only Fuseki/Oxigraph route above) | Oracle's own docs pages confirm the RDF/SPARQL feature exists inside Always Free Autonomous Database ([docs.oracle.com — Using Graph Studio](https://docs.oracle.com/en/cloud/paas/autonomous-database/csgru/sparql-rdf-interpreter.html), checked 2026-09-19); the *endpoint deployment itself* still requires standing up an RDF Server layer yourself (per Oracle's own tutorial), so this is a managed-database-plus-self-deployed-endpoint hybrid, not a single-click hosted SPARQL product — closer to the Fuseki/Oxigraph-on-Oracle-Always-Free row above than to a turnkey vendor SaaS, but with Oracle managing the underlying database tier instead of you |

**Google Cloud / Azure named near-misses:** the original "no offering found"
was a true statement but an incomplete one — both platforms have graph
database products, just not RDF/SPARQL ones. **Azure Cosmos DB for Apache
Gremlin** is a fully-managed **property graph** service using Gremlin
(TinkerPop) as its query language; Microsoft's own docs and community
threads confirm it has **no SAIL interface and no native RDF/SPARQL
support** — community efforts exist to bolt on RDF serialization, but
that is not a first-party feature
([learn.microsoft.com/.../gremlin/overview](https://learn.microsoft.com/en-us/azure/cosmos-db/gremlin/overview);
[groups.google.com/g/gremlin-users — "RDF serialisation on Cosmos DB"](https://groups.google.com/g/gremlin-users/c/sfQhBsuUSeo),
checked 2026-09-19). **Google Spanner Graph** is Google's graph query
capability on Spanner; the one source found situates it alongside Neptune,
Cosmos DB, Neo4j, and JanusGraph as an IDE-compatible property-graph target
(via the third-party `gdotv` tool), which is consistent with it being a
property-graph offering (like Cosmos/Gremlin), not RDF/SPARQL — this
inference was not confirmed against Google's own Spanner Graph
documentation directly in this pass, so treat the Spanner Graph
classification as **secondary-sourced, not primary-confirmed**, unlike the
Cosmos DB finding above.

### Net on question 1

No option in the primary named-list survey is a **confirmed** direct,
like-for-like analog of Atlas M0 (a vendor that keeps your own custom data
online, publicly reachable over TLS, for free, indefinitely, with a
documented idle-pause rather than an outright teardown, and a primary
pricing page spelling out every limit). Three approximations emerged, in
descending order of how close each comes and how well-confirmed each is:

- **TriplyDB** (found in the broader sweep) — reported by multiple
  secondary sources as the closest match in shape (bring-your-own-data,
  free, public SPARQL endpoint, capped at 1M triples), but **not
  independently confirmed against a primary pricing page** in this pass.
  This is the one candidate worth a direct, primary-source follow-up before
  treating it as real.
- **Wikibase Cloud** — vendor-hosted and appears free-forever in practice,
  but the data model is Wikibase's own (items/statements/qualifiers), not
  a bring-your-own-triples store — using it would mean re-modeling the
  Decision Graph Bundle as Wikibase items rather than loading RDF as-is.
- **Oracle Cloud Always Free** (either self-hosted Fuseki/Oxigraph on an
  Always Free compute VM, or Oracle's own Autonomous Database RDF Semantic
  Graph feature inside the Always Free database tier) — a real generic
  SPARQL 1.1 endpoint you (mostly) control, free-forever infrastructure,
  confirmed via Oracle's own docs pages, but still requires deploying and
  operating the SPARQL-serving layer yourself (TLS, auth, and — for the
  self-hosted-Fuseki route — patching and uptime — are your problem either
  way, with no vendor SLA on the endpoint itself).

---

## 2. Ecosystem fit — Decision Graph Bundle shape onto RDF/SPARQL

The Decision Graph Bundle (per
`.scratch/mongodb-v2-agent-interface/research/01-atlas-free-vs-bundle-size.md`,
itself read from `edgar_warehouse/serving/subject_bundle_read.py` /
`subject_feature_screen.py`) has two structurally different parts:

**Relationship edges (`IS_INSIDER`, `EMPLOYED_BY`) — natural fit.** These
are already binary, typed, directed relationships between two entities
(person ↔ issuer). That is exactly the subject-predicate-object shape RDF
triples were designed for, e.g.:

```
:person123  ex:isInsiderOf     :cik0000320193 .
:person123  ex:employedBy      :cik0000320193 .
```

This is a closer conceptual match to RDF than to a document store — a
graph database (the platform's own MDM graph work already runs on
Snowflake's Neo4j Graph Analytics Native App, a **property graph**, not RDF
— see `CONTEXT.md`/CLAUDE.md "Graph storage" note) is the same general
family of shape SPARQL targets, though a property graph and RDF triples are
not identical models (property graphs attach key/value properties directly
to nodes/edges; RDF has no native edge-properties concept without an
n-ary-relation pattern — see below).

**As-Of Decision Features (tabular, per-CIK, watermark-dated) — awkward
fit.** `build_subject_feature_screen` returns one flat numeric vector
(19 `PURE_SEC_FEATURE_KEYS`, e.g. `revenue`, `ebitda`, `roe`) per CIK per
period, each row carrying a **copy of the watermark identity**
(`business_date`, `gold_run_id`, `graph_generation_id`,
`decision_contract_version`) for provenance. A bare RDF triple
`(:cik0000320193, ex:revenue, "394328000000"^^xsd:decimal)` has no room to
attach *which* fiscal period or *which* watermark that number is valid for
— that context has to live somewhere. W3C's own guidance on this exact
problem, "Defining N-ary Relations on the Semantic Web"
([w3.org/TR/swbp-n-aryRelations](https://www.w3.org/TR/swbp-n-aryRelations/),
checked 2026-09-19), states plainly that RDF's binary-predicate model needs
one of several patterns to add a third/fourth dimension (time, source,
confidence) to a fact — an intermediate "relation" resource, reification
(explicitly **not recommended** by that same document for general use,
since a reified statement has no logical connection back to an asserted
one), singleton properties, or RDF-star (quoted triples, a newer
extension). None of these is a bare triple; all require extra resources or
non-standard extensions per fact. This is real added modeling work that
the existing flat-JSON-document shape (Mongo) and the relational SQL
sketches (`infra/snowflake/sql/decision_contract/`) do not need, since a
JSON object or a SQL row already has native "extra columns" for period and
watermark alongside the value.

The universe-wide **Feature Screen** (`rows[]` for all CIKs in one payload)
does not have RDF's version of the 16 MiB single-BSON-document problem the
prior Mongo research measured (line 264–284 of the prior research file:
Feature Screen as one Mongo document is illegal past ~12,387 rows) — a
triple store has no equivalent single-document size cap, since triples are
stored in one graph/dataset rather than one document. But every row still
carries the same n-ary/provenance problem described above, multiplied by
however many rows exist.

**Prior art / ontologies:**

- **schema.org** — has `Organization`, `Person`, and an `employee` property
  ("Someone working for this organization"), and its own documentation is
  explicit that it is **not** meant as a domain ontology: "The type
  hierarchy presented on this site is not intended to be a 'global
  ontology' of the world" and "schema.org is not intended as a universal
  ontology" ([schema.org/docs/datamodel.html](https://schema.org/docs/datamodel.html),
  checked 2026-09-19, quoted directly from the primary source). It could
  supply generic `Organization`/`Person`/`employee` vocabulary for the
  `EMPLOYED_BY` edge, but has no concept for SEC-specific relationships
  like Section 16 insider status, beneficial ownership thresholds, or
  fiscal-period-scoped financial factors.
- **FIBO (Financial Industry Business Ontology)**, maintained by the EDM
  Council and standardized under OMG, is a real, actively-maintained,
  domain-specific ontology for finance — modules include **Business
  Entities** ("business concepts... used for data governance,
  interoperability, and... regulatory reporting"), **Foundations**
  ("concepts and relationships about people, organizations, places, and...
  contracts"), and **Financial Business and Commerce** (covers "financial
  intermediaries, registrars and regulators")
  ([github.com/edmcouncil/fibo](https://github.com/edmcouncil/fibo), checked
  2026-09-19). These modules are the closest conceptual fit found for
  issuer/insider/employment-shaped data. **Unconfirmed:** whether FIBO has
  an explicit class/property for SEC Section 16 "insider" status or
  beneficial-ownership-percentage semantics by name — this pass could not
  browse the live FIBO ontology viewer
  ([spec.edmcouncil.org/fibo/ontology](https://spec.edmcouncil.org/fibo/ontology))
  to check specific class names, only its GitHub README-level module
  descriptions. A secondary source (a consultancy blog, not the EDM Council
  itself) put FIBO's 2026/Q1 Production release at roughly 2,400 classes —
  flagged as secondary-sourced, not independently verified against a
  primary FIBO release note in this pass.

---

## 3. Query language accessibility for a downstream LLM agent

**Primary benchmark found: SM3-Text-to-Query** (NeurIPS 2024 Datasets &
Benchmarks Track; [arxiv.org/abs/2411.05521](https://arxiv.org/abs/2411.05521);
code/data at [github.com/jf87/SM3-Text-to-Query](https://github.com/jf87/SM3-Text-to-Query),
checked 2026-09-19). It generated 10,000 synthetic natural-language
question/query pairs (40,000 across all four targets) over the same
synthetic medical dataset (Synthea, SNOMED-CT-based) represented four ways:
PostgreSQL (SQL), MongoDB (MQL), Neo4j (Cypher), and GraphDB (SPARQL/RDF) —
so query language is the only varying factor, not the underlying data.
Models tested: "several relevant closed and open-source LLMs from OpenAI,
Google, and Meta," reported by a walkthrough of the same benchmark
(Jonathan Fürst, one of the paper's authors) as including GPT-3.5,
Llama3-70b, and Gemini 1.0
([towardsdatascience.com — "Can LLMs talk SQL, SPARQL, Cypher, and MongoDB
Query Language (MQL) equally well?"](https://towardsdatascience.com/can-llms-talk-sql-sparql-cypher-and-mongodb-query-language-mql-equally-well-a478f64cc769/),
checked 2026-09-19).

**Zero-shot execution-accuracy results (best model per language, with
schema provided):**

| Query language | Zero-shot execution accuracy |
| --- | --- |
| SQL | **47.05%** |
| Cypher | 34.45% |
| MQL (MongoDB) | 21.55% |
| SPARQL | **3.3%** |

With **five-shot** prompting (a handful of worked examples in-context),
SPARQL's accuracy rose to about **30%** in the same study — still not
matching SQL zero-shot, but a large relative jump, indicating the gap is
substantially an in-context/training-exposure effect rather than an
unfixable structural one.

**Author's own explanation:** correlates the ranking with how often each
language appears in what LLMs were trained on, citing Stack Overflow post
counts — **SQL 673K posts, MongoDB/MQL 176K, Cypher/Neo4j 33K, SPARQL
6K** — and states explicitly that training-data frequency/recency "significantly
impact[s] LLM performance," directly matching the accuracy ranking above.

**A second data point, now identified and fetched:** the "3x SPARQL
accuracy" figure traces to Sequeda, Allemang & Jacob, "A Benchmark to
Understand the Role of Knowledge Graphs on Large Language Model's Accuracy
for Question Answering on Enterprise SQL Databases"
([arxiv.org/abs/2311.07509](https://arxiv.org/abs/2311.07509), Nov 2023,
data.world). **This measures a different thing than SM3 above and should
not be read as a contradicting SPARQL-generation-accuracy number.** Per
the abstract (fetched directly): GPT-4 answering questions with zero-shot
prompts **directly against an enterprise SQL database** (insurance domain)
scored **16%** answer accuracy; the same questions answered **via a
knowledge-graph representation of that same SQL database** (an ontology +
mappings layer on top) scored **54%** — a 38-point / ~3.4x jump. Two
important distinctions from the SM3 comparison:

1. This is **end-to-end answer accuracy** (did the system produce the
   right answer to a natural-language question), not **query-syntax
   generation accuracy** (did the model write a syntactically/semantically
   correct query) — SM3 measures the latter directly.
2. The abstract does not state which query language was actually run
   against the knowledge graph — it names the KG/ontology layer as the
   independent variable, not SPARQL specifically, so this paper is evidence
   that **adding a semantic/ontology layer improves LLM question-answering
   accuracy over raw SQL schemas**, not direct evidence that **SPARQL
   syntax is easier for an LLM to generate than SQL syntax** (which is the
   narrower question SM3 answers, and where SPARQL scored worst).

Both findings can be true simultaneously: an LLM can be worse at writing
raw SPARQL syntax (SM3) while still answering better when a well-modeled
ontology disambiguates the question first (Sequeda et al.) — the ontology
layer's disambiguation benefit and the target query language's syntax
difficulty are separate variables. Neither this research pass nor the two
papers themselves reconcile them directly.

A related paper was found but not fetched in full: "Are we too focused on
single query language? Investigating text-to-SQL/SPARQL/Cypher task
complexity via fine-tuning unbiased T5 models" (ScienceDirect,
[sciencedirect.com/science/article/pii/S0925231226016000](https://www.sciencedirect.com/science/article/pii/S0925231226016000)).
Title and venue only confirmed; specific numbers not extracted in this
pass — flagged as a pointer for further reading, not a cited data point.

**MongoDB comparison:** the only benchmark found that puts MQL and SPARQL
head-to-head under identical conditions is SM3 above — MQL (21.55%
zero-shot) outperforms SPARQL (3.3%) by a wide margin on the same task
family, though both lag SQL.

**Plain REST/JSON comparison: no evidence found.** This research pass did
not find a benchmark comparing SPARQL generation against an LLM agent
calling a fixed, documented REST/JSON API (i.e., tool-use / function-calling
against a small set of known endpoints, rather than free-form query-language
generation). State this explicitly per the task's instruction: **no such
evidence was found**, not "REST is better/worse" — a fixed API changes the
task shape entirely (bounded tool selection vs. open-ended query synthesis)
and is generally treated as a separate research area (tool-use accuracy)
from text-to-query benchmarks, but no source quantifying that difference
for this specific comparison was located.

**Tooling-maturity facts (not benchmark claims):** SPARQL 1.1 has been a
stable W3C Recommendation since 2013; open tooling exists and is mature at
the protocol level — Oxigraph and Fuseki both bundle a YASGUI-style web
query IDE out of the box, and `rdflib` is a long-established Python client
library. Large public SPARQL endpoints (Wikidata Query Service, DBpedia)
are commonly used as LLM SPARQL-generation targets in the academic
literature found above. This is a fact about protocol/tooling stability,
separate from and not a substitute for the LLM-generation-accuracy
evidence above, which shows current LLM proficiency at *writing* SPARQL is
comparatively weak.

---

## 4. Cost beyond free tier (context only, not a recommendation)

| Option | Rough paid-tier cost shape | Confidence |
| --- | --- | --- |
| **Amazon Neptune** (provisioned) | On-demand smallest instance (`db.t3.medium`/`db.t4g.medium`) **≈ $0.348/hr ≈ $254/month** (US East N. Virginia), separate from the 30-day trial | Official AWS figure, from [aws.amazon.com/neptune/pricing](https://aws.amazon.com/neptune/pricing/), checked 2026-09-19 |
| **Amazon Neptune Serverless** | Billed per Neptune Capacity Unit (NCU)-hour; **from $0.1098/NCU-hour**, 1 NCU ≈ 2 GB RAM + proportional CPU; a "practical minimum around $80/month" figure appeared in third-party cost-breakdown blogs (Usage.ai, Wring), **not** a line item on AWS's own pricing page | NCU rate is official; the ~$80/month "minimum" is a third-party estimate, flagged unconfirmed against AWS's own materials in this pass |
| **Neptune storage** | $0.10/GB-month + $0.20 per million I/O requests | Third-party-summarized in the same blogs; not independently re-verified against the live AWS calculator |
| **Ontotext GraphDB** | No public self-serve price list. One AWS Marketplace listing found: "GraphDB Managed Evaluation (non-production)," **$3,990/month**, 1-month contract, explicitly non-production. Enterprise licensing is a separate vendor-billed relationship with no published number. | Marketplace figure from search-result summary, not independently re-opened on the AWS Marketplace page itself — flag as secondary-sourced |
| **Stardog** | No public pricing anywhere found; the pricing page's own FAQ says a sales call is required to get a number | Confirmed absence of public pricing, from [stardog.com/pricing](https://www.stardog.com/pricing/) |
| **Self-hosted Jena Fuseki / Oxigraph beyond free compute** | Not vendor SaaS pricing — the realistic floor is a small paid VM (a few to roughly a dozen USD/month order of magnitude on providers like a paid Oracle Cloud shape, DigitalOcean, or Hetzner) if the free-compute route is outgrown | **Not independently priced in this pass** — flagged as a rough, unconfirmed order-of-magnitude estimate only, not a quoted price from any specific vendor's current rate card |
| **Wikibase Cloud** | No paid tier found in sources checked; hosting policy pages describe the free offering with no paid-tier mention | Unconfirmed-negative — a dedicated pricing page was not located |
| **Virtuoso OSE** | No managed free-or-paid SaaS tier found; commercial "Virtuoso Enterprise Edition" exists from OpenLink but its pricing was not looked up in this pass | Not researched beyond confirming OSE itself is self-host-only |

---

## Sources

Official/primary:

- https://www.stardog.com/pricing/ (checked 2026-09-19)
- https://www.stardog.com/stardogexpress/ (checked 2026-09-19)
- https://graphdb.ontotext.com/documentation/11.3/licensing.html (checked 2026-09-19)
- https://www.ontotext.com/services/graphdb-managed-services/ (checked 2026-09-19)
- https://aws.amazon.com/neptune/pricing/ (checked 2026-09-19)
- https://aws.amazon.com/about-aws/whats-new/2022/04/amazon-neptune-offers-free-trial/ (checked 2026-09-19)
- https://fly.io/docs/about/discontinued-plans/ (checked 2026-09-19)
- https://render.com/docs/faq (checked 2026-09-19)
- https://meta.wikimedia.org/wiki/Wikibase/Wikibase.cloud (checked 2026-09-19)
- https://www.mediawiki.org/wiki/Wikibase/Wikibase.cloud/Hosting_policy (checked 2026-09-19)
- https://github.com/openlink/virtuoso-opensource (checked 2026-09-19)
- https://github.com/oxigraph/oxigraph (checked 2026-09-19)
- https://gdb-engines.com/db/oxigraph/ (checked 2026-09-19)
- https://www.w3.org/TR/swbp-n-aryRelations/ (checked 2026-09-19)
- https://schema.org/docs/datamodel.html (checked 2026-09-19, quoted directly)
- https://github.com/edmcouncil/fibo (checked 2026-09-19)
- https://arxiv.org/abs/2411.05521 (SM3-Text-to-Query, NeurIPS 2024; checked 2026-09-19)
- https://github.com/jf87/SM3-Text-to-Query (checked 2026-09-19)
- https://towardsdatascience.com/can-llms-talk-sql-sparql-cypher-and-mongodb-query-language-mql-equally-well-a478f64cc769/ (checked 2026-09-19)
- https://arxiv.org/abs/2311.07509 (Sequeda/Allemang/Jacob KG-vs-SQL QA accuracy; abstract fetched directly, checked 2026-09-19)
- https://docs.oracle.com/en/cloud/paas/autonomous-database/csgru/sparql-rdf-interpreter.html (checked 2026-09-19)
- https://learn.microsoft.com/en-us/azure/cosmos-db/gremlin/overview (checked 2026-09-19)

Secondary (flagged inline above where used):

- https://medium.com/oracledevs/run-always-free-docker-container-on-oracle-cloud-infrastructure-c88e36b65610
- https://www.saaspricepulse.com/blog/flyio-free-tier-2026
- https://www.usage.ai/blogs/aws/database-savings-plans/neptune-pricing/
- https://wring.co/blog/aws-neptune-pricing-guide
- https://www.sciencedirect.com/science/article/pii/S0925231226016000 (title/venue only, not fetched)
- https://groups.google.com/g/gremlin-users/c/sfQhBsuUSeo (Cosmos DB RDF community thread, checked 2026-09-19)
- TriplyDB / AllegroGraph Cloud / QLever / Dydra / Fluree — search-result summaries only; no primary pricing page independently fetched (see §1 "Additional vendors" table for per-vendor confidence)

In-repo:

- `docs/adr/0009-mongo-decision-projection.md`
- `.scratch/mongodb-v2-agent-interface/research/01-atlas-free-vs-bundle-size.md`
- `.scratch/agent-decision-contract/research/10-json-mongodb-agentic-data-plane.md`
- `edgar_warehouse/serving/subject_bundle_read.py`
- `edgar_warehouse/serving/subject_feature_screen.py`
- `edgar_warehouse/serving/decision_contract.py`
- CLAUDE.md "Graph storage" note (Snowflake Neo4j Graph Analytics Native App = property graph, not RDF, and not an external Neo4j)

**Not found / not recovered in this pass:**
`.scratch/agent-decision-v1-inputs/research/10-free-public-agentic-databases.md`
(the file this research was asked to match) — see note at top of this
document.
