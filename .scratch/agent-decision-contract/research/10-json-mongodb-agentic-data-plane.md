# JSON documents / MongoDB as an end-user agentic data plane

Ticket: `.scratch/agent-decision-contract/issues/10-json-mongodb-as-agentic-data-plane.md`

Scope: in-repo ADRs, glossary, serving modules, SQL sketches, dependencies,
and this map's destination. No vendor MongoDB/JSON marketing. Live Snowflake
was not re-queried; live emptiness of `EDGARTOOLS_DECISION` is taken from
[research/01-live-decision-contract-objects.md](01-live-decision-contract-objects.md).

**Locked facts this ticket must not blur:**

- ADR 0001 currently says agents read **Snowflake only**.
- ADR 0001 v1 **delivery** is the **Snowflake Decision Contract**.
- This map's destination is an implementation-ready **Snowflake** Decision
  Contract plan, not a new document store.

Verdict in one line: **do not make MongoDB or a JSON document store the
end-user Agent Decision Surface for v1, instead of or beside Snowflake.**
JSON already exists as the *payload shape* of a Decision Graph Bundle
(Python `dict`); that is serialization, not a second SoE.

---

## Primary sources

- `docs/adr/0001-agent-decision-surface-first.md`
- `docs/adr/0002-silver-soe-edgartools-exclusive.md`
- `docs/adr/0006-sec-bronze-ledger-silver-authority.md`
- `docs/doctrine-data-plane.md`
- `docs/product-questions-and-dashboards.md`
- `docs/subject-bundle-read.md`
- `docs/subject-feature-screen.md`
- `docs/dashboard-decision-contract.md`
- `docs/project-overview.md`
- `CONTEXT.md` (Agent System of Engagement; Agent decision support)
- `edgar_warehouse/serving/subject_bundle_read.py` (`build_issuer_subject_bundle`)
- `edgar_warehouse/serving/subject_feature_screen.py` (`build_subject_feature_screen`)
- `edgar_warehouse/serving/decision_contract.py` (`evaluate_agent_grade`, `DecisionWatermark.to_dict`)
- `edgar_warehouse/serving/dashboard_modes.py`
- `edgar_warehouse/serving/dashboard_query_registry.py`
- `edgar_warehouse/serving/watermark_aggregator.py` (`JsonAlignmentStore`)
- `edgar_warehouse/serving/targets/snowflake.py` (`SnowflakeTarget`, `default_serving_target`)
- `infra/snowflake/sql/decision_contract/{01,02,03}_*.sql`
- `infra/snowflake/sql/bootstrap/15_decision_schema.sql`
- `infra/snowflake/streamlit/streamlit_app.py` (`_render_agent_view_company`)
- `pyproject.toml`, `uv.lock`
- `.scratch/agent-decision-contract/map.md`
- `.scratch/agent-decision-contract/research/02-in-repo-contract-semantics.md`
- `.scratch/agent-decision-data-plane/spec.md`

---

## 1. Current end-user agent read path

Three layers exist. Only Snowflake is the declared Agent SoE. None of them
is MongoDB.

### Declared plane (ADR / glossary)

`CONTEXT.md` **Agent System of Engagement**:

> Snowflake Decision Contract objects only; agents never read silver or bronze
> directly.

`docs/adr/0001-agent-decision-surface-first.md` ingest header:

> agents still read **Snowflake only**

Locked v1 delivery table in the same ADR: **Delivery = Snowflake Decision
Contract**. Unit of read is a **Decision Graph Bundle** rooted at CIK.

`docs/doctrine-data-plane.md` plane table: Trading agent SoE is **Snowflake
Decision Contract**; not Silver, bronze, or Streamlit.

`docs/product-questions-and-dashboards.md` product table:

> **Agent delivery (v1)** | **Snowflake Decision Contract (A)** | Published
> Snowflake objects are the contract; audit UI reads the same; **S3/API
> optional later**

That last clause is the only in-repo door for a later JSON/HTTP serving
layer. It is explicitly *later*, not v1, and it does not name MongoDB.

`CONTEXT.md` **Snowflake Decision Contract**:

> published Snowflake objects (views, tables, or procedures) that return
> Decision Graph Bundles or their relational equivalent under a declared
> schema version; the Human Audit View queries these same objects.

Avoid list on that term: Streamlit-only path, agent-private tables that
diverge from audit UI, **S3 file dump as the primary contract**, undocumented
ad-hoc gold joins.

`CONTEXT.md` **Deferred Access Control** allows a later pluggable access
layer ("Snowflake (or equivalent) session") so OAuth can wrap the *same*
contract. "Equivalent" is session/auth, not a second document database.

### Snowflake objects (intended, not yet live)

Intended agent objects live under `EDGARTOOLS_DECISION`:

| Object | Role | Source |
| --- | --- | --- |
| `SUBJECT_FEATURE_SCREEN` | Multi-subject ranking | `01_subject_feature_screen.sql` |
| `SUBJECT_BUNDLE_READ` / `SUBJECT_BUNDLE_READ_ISSUER` | Single-subject read | `03_dashboard_contract.sql` (identity + features; **no neighborhood sections**) |
| `BUNDLE_HOLDERS_OF_SUBJECT` / `BUNDLE_AUDITOR` | Neighborhood sketches | `02_subject_bundle_read_issuer.sql` (not applied / not granted) |
| `DECISION_CONTRACT_PUBLICATION` | Operator READY assertion | `03_dashboard_contract.sql` |
| `DECISION_CONTRACT_STATUS` | Fail-closed ready view | publication READY + ALIGNED + coverage + live `GRAPH_ACTIVE_POINTER` |
| `DECISION_CONTRACT_DISPLAY_STATUS` / `SUBJECT_BUNDLE_DISPLAY_ISSUER` | Human Agent View even when not READY | same file; `READINESS_STATE` |

Live prod ([research/01](01-live-decision-contract-objects.md)): schema
`EDGARTOOLS_DECISION` exists and is **empty** (zero tables/views). Feature
screen and issuer bundle objects **do not exist**. Publication table does
not exist. Bootstrap `15_decision_schema.sql` only creates the empty
container so Terraform reader grants have a schema to attach to.

Agent View SQL never mentions `EDGARTOOLS_GOLD.` or
`NEO4J_GRAPH_MIGRATION.` in the query text
(`tests/architecture/test_dashboard_decision_contract.py`). Those schemas
are still the *upstream* of the contract views.

### Python dicts / JSON-serializable payloads (canonical semantics today)

Canonical contract semantics are unit-tested Python, not SQL
([research/02](02-in-repo-contract-semantics.md)).

- `build_issuer_subject_bundle(...)` → `dict[str, Any]`
- `build_subject_feature_screen(...)` → `dict[str, Any]`
- `AgentGradeResult.to_dict()` / `DecisionWatermark.to_dict()` → `dict`

These dicts are JSON-serializable nested documents. They are **not written
to a document store**. Callers inject gold/graph rows; the modules do not
query Snowflake or Mongo.

There is no CLI that exports a Subject Bundle as a JSON file for agents.
`edgar-warehouse reconcile-decision-watermark` (`cli.py`
`_handle_reconcile_decision_watermark`) prints a JSON **alignment** payload
and optionally persists `JsonAlignmentStore` — observe-only watermark
rollup, explicitly not an INSERT into `DECISION_CONTRACT_PUBLICATION`.

### Streamlit Human Audit View

`infra/snowflake/streamlit/streamlit_app.py` `_render_agent_view_company`
runs `registered_query("agent.subject_bundle")` against
`EDGARTOOLS_DECISION.SUBJECT_BUNDLE_DISPLAY_ISSUER` (a **row**, not the
Python nested bundle). It renders a pandas DataFrame plus a freshness
dict. Bounded CSV download exists; no JSON bundle download.

Agent View vs Explore is Python-only (`dashboard_modes.py`): default
fail-closed to `agent_view`; allowlist is Snowflake object names.

`AGENT_VIEW_QUERIES` (`dashboard_query_registry.py`):

| Query id | Snowflake object |
| --- | --- |
| `agent.contract_status` | `DECISION_CONTRACT_DISPLAY_STATUS` |
| `agent.subject_search` | `DASHBOARD_SUBJECT_RESOLVER` |
| `agent.subject_bundle` | `SUBJECT_BUNDLE_DISPLAY_ISSUER` |

### What is *not* the agent path

| Surface | Why not agent-grade |
| --- | --- |
| `edgar_warehouse/serving/targets/snowflake.py` `SnowflakeTarget` | Gold **Parquet** export for native S3 pull, not Decision Graph Bundles |
| `default_serving_target()` | Always `SnowflakeTarget`; no Mongo/JSON target |
| MDM FastAPI `/graph` (`edgar_warehouse/mdm/api/routers/graph.py`) | Reads **Postgres** `mdm_relationship_instance`; operator/API, not the Decision Contract |
| Explore Mode gold SQL | Explicitly not Trading Decision input |
| Silver DuckDB | ADR 0001 / 0002: agents must not query silver |
| Bronze S3 | Evidence plane, not agent SoE |
| `JsonAlignmentStore` | Operator alignment scratch JSON |

End-to-end intended path:

```text
SEC → edgartools → Bronze → Silver → MDM/graph + gold export
  → Snowflake SOURCE / GOLD / NEO4J_GRAPH_MIGRATION
  → EDGARTOOLS_DECISION views (Snowflake Decision Contract)
  → trading agent (SQL/session) and SiS Agent View (same objects)
```

Python dict builders sit beside that as the in-repo **shape specification**
until SQL matches them.

---

## 2. Does any MongoDB or JSON contract already exist?

**MongoDB: no.**

Repo-wide search (`mongodb`, `pymongo`, `mongoengine`, `motor`,
`documentdb`, `atlas`) on `pyproject.toml`, `uv.lock`, Terraform, Python,
SQL, YAML, markdown: **zero hits** except the country name `MONGOLIA` in
`examples/dashboard/edgar_universe_dashboard.py`.

`pyproject.toml` extras: `s3`, `snowflake`, `dashboard`, `mdm`,
`mdm-runtime`, `market`. No mongo extra. `uv.lock` has no `pymongo` /
`mongo`. No Terraform DocumentDB/Atlas module. Agents.md / this map:
AWS-only; do not introduce another storage target.

**JSON *contract* (versioned agent schema as documents): no.**

There is no JSON Schema, OpenAPI for bundles, Mongo collection, or S3
prefix of Decision Graph Bundle JSON. `infra/snowflake/sql/decision_contract/`
uses relational columns (`STRING`, `DATE`, `TIMESTAMP_TZ`). No `VARIANT`,
`OBJECT_CONSTRUCT`, or `PARSE_JSON` in those three SQL files.

JSON that *does* exist is not the Agent Decision Surface:

| JSON | Purpose |
| --- | --- |
| SEC bronze `CIK*.json`, ticker snapshots | Ingest evidence |
| Run / Snowflake `run_manifest.json` | Pipeline bookkeeping |
| `JsonAlignmentStore` | Observe-only watermark alignment |
| `ecs_sizing_canary.extract_json_documents` | CloudWatch log parsing |
| CLI stdout `json.dumps` of parity / watermark | Operator diagnostics |
| Graph `PROPERTIES VARIANT` (`snowflake_graph.py`) | Graph edge/node properties, not Decision Contract |

`CONTEXT.md` already rejects **S3 file dump as the primary contract**.

---

## 3. Decision Graph Bundle is already document-shaped — that is not Mongo

`build_issuer_subject_bundle` (`edgar_warehouse/serving/subject_bundle_read.py`)
returns one nested payload:

```text
{
  bundle_subject_cik, bundle_kind: "issuer",
  decision_contract_version,
  decision_watermark_identity: {business_date, gold_run_id,
                                graph_generation_id, decision_contract_version},
  agent_grade, agent_grade_reasons,
  include_neighborhood_history,
  sections: {
    insiders, employment, holders_of_subject,
    subject_as_manager_portfolio, auditor, has_parent,
    subject_features, adv
  }
}
```

Each section is itself a small document: `coverage` (`present` / `empty` /
`unavailable` / `not_applicable`) plus `rows` and section-specific metadata
(holdings lag, PCAOB preference, parent inventory, FY/interim feature
vectors). Locked by `tests/unit/test_subject_bundle_read.py`.

`build_subject_feature_screen` is a document wrapping a **flat row list**
(`universe_size`, `rows[]` with per-CIK FY/interim vectors and coverage).

That shape is exactly what CONTEXT calls a Decision Graph Bundle: "a
multi-entity **payload** rooted at one subject". ADR 0001 unit of read is
that payload. Snowflake Decision Contract is defined as objects that return
"**Decision Graph Bundles or their relational equivalent**".

Implications:

1. **JSON serialization of the Python dict is free** (`json.dumps(bundle)`).
   That does not create a document store.
2. **A Mongo collection of those dicts would be a second copy** of the
   contract, keyed by CIK + watermark, with its own freshness, auth, and
   fail-closed publication. Dual truth is the failure mode ADR 0001
   rejected for UI-first ("rework when the agent lands; dual truth") and
   CONTEXT rejects for "agent-private tables that diverge from audit UI".
3. **SQL 03 already chose the relational equivalent**, and it is *narrower*
   than the Python document (identity + feature-screen columns; no
   neighborhood). Closing that gap is this map's Snowflake work
   (neighborhood sections, bronze digest, universe intersection) — not a
   reason to stand up Mongo.
4. **Snowflake VARIANT** could hold the nested bundle *inside*
   `EDGARTOOLS_DECISION` and would still be the Snowflake Decision
   Contract. Graph already uses `VARIANT`/`OBJECT_CONSTRUCT_KEEP_NULL` for
   properties. Decision-contract SQL does not. That is an implementation
   choice for later Snowflake tickets, still not Mongo.

Mongo would only add: a new runtime, secrets, IAM, backup, and a write
path that must stay aligned with gold + graph + publication. The bundle
shape does not require it.

---

## 4. What ADR 0001 / CONTEXT would have to change; what would stay Snowflake

To make **MongoDB** (or a JSON document store) the agent plane **instead of**
Snowflake, these accepted texts would need a new ADR (0001 is accepted;
doctrine says do not re-introduce superseded ideas without a new ADR).

| Text | Today | Would have to change |
| --- | --- | --- |
| ADR 0001 header | "agents still read **Snowflake only**" | Agents read Mongo/JSON (or Snowflake *and* Mongo) |
| ADR 0001 locked table | Delivery = Snowflake Decision Contract | Delivery = Mongo collection / JSON files / dual |
| ADR 0001 rejected | UI-first dual truth | Dual Snowflake+Mongo is the same dual-truth class |
| CONTEXT Agent SoE | Snowflake Decision Contract objects only | New SoE name and avoid-list |
| CONTEXT Snowflake Decision Contract | v1 delivery of the Agent Decision Surface | Demote to warehouse/analytics only, or keep as source of a projection |
| CONTEXT Avoid on that term | S3 file dump as primary contract | Explicitly allow or still forbid JSON-on-S3 |
| CONTEXT Deferred Access Control | Operator Snowflake session; OAuth later | Mongo auth/network + secret containers |
| Doctrine one-sentence | "form trading decisions only from aligned **Snowflake** projections" | Rewrite the last clause |
| Doctrine plane table | Trading agent = Snowflake Decision Contract | New row; "Agent may read silver" style supersession |
| Product table | Agent delivery v1 = Snowflake; **S3/API optional later** | Promote "later" into v1, or add Mongo |
| Architecture tests | Agent View SQL scoped to `EDGARTOOLS_DECISION` | New allowlist / dual-path tests |
| This map destination | Remaining **Snowflake** Decision Contract | Different map |

**Would stay Snowflake even if a later serving layer projected JSON:**

| Plane | Why it stays |
| --- | --- |
| Ingest | SEC → edgartools → Bronze S3 → Silver; ADR 0006; not an agent read |
| Gold | `EDGARTOOLS_GOLD` dbt dynamic tables; Explore + contract upstream |
| Graph | Snowflake Neo4j Graph Analytics Native App; `GRAPH_ACTIVE_POINTER` is the agent-grade generation pin |
| MDM operational store | Snowflake-hosted Postgres, not agent SoE |
| Native S3 pull / SOURCE | Warehouse load path |
| Human Audit View hosting | Streamlit-in-Snowflake over the **same** contract objects |
| Publication fail-closed | `DECISION_CONTRACT_PUBLICATION` + pointer join is a Snowflake assertion |

Mongo **instead of** Snowflake for agents would still need Snowflake for
gold, graph generation, ingest, and (today) SiS audit — unless SiS were
rewritten against Mongo, which is a greenfield UI path this map lists as
out of scope.

Mongo **beside** Snowflake is worse for v1: two agent surfaces, two
watermarks, two READY gates, and no forcing function they match. That
violates "Human Audit View queries these same objects" and Agent View
"Same surface a trading agent would pin" (`AGENT_VIEW_BANNER`).

Map constraints that Mongo also breaks without an explicit architecture
change: "AWS-only. Do not introduce another cloud, registry, workflow
engine, **storage target**, or secret-management path." Out of scope:
"Greenfield rewrite, new microservice, external Neo4j, DuckDB replacement."

---

## 5. Fit with this map vs a later serving-layer effort

This map destination (`.scratch/agent-decision-contract/map.md`):

> An implementation-ready, decision-complete plan for the remaining
> **Snowflake Decision Contract**: composite Decision Watermark and
> agent-grade gate, Subject Feature Screen, issuer Subject Bundle Read,
> and Streamlit-in-Snowflake Agent View versus Explore, consistent with
> ADR 0001 and ADR 0006.

Predecessor spec (`.scratch/agent-decision-data-plane/spec.md`) Front B:

> A **thin Decision Contract** layer **in Snowflake** … No new agent
> runtime in AWS.

JSON/Mongo as the end-user plane is listed under this map's **Not yet
specified** only as a research question; the destination itself is already
Snowflake. Answering "yes, Mongo/JSON store now" would reopen ADR 0001 and
leave this map.

**In this map (keep):**

- Finish Snowflake contract objects so they match Python bundle semantics
  (universe intersection, bronze digest in watermark, neighborhood
  sections, Agent View vs Explore).
- Treat Python `dict` payloads as the document-shaped spec the SQL
  (relational or later VARIANT) must project.
- Agents may *materialize* JSON in-process from Snowflake rows; that is
  client serialization, not a new SoE.

**Later serving-layer effort (not this map), and only if a new ADR says so:**

- Product table already: **S3/API optional later**.
- A read-only HTTPS/JSON API or S3 snapshot that **projects the published
  Snowflake contract** (same watermark, same version, same READY gate),
  with Human Audit View still pinned to Snowflake, would be a serving
  convenience — still not Mongo as SoE.
- Mongo as a cache of that projection would need a dual-truth design
  review; nothing in-repo justifies it today (no driver, no module, no
  ADR option considered).

**Do not do in this map:**

- Introduce `pymongo` / DocumentDB / Atlas.
- Make JSON files on S3 the primary agent contract (CONTEXT Avoid).
- Dual-write bundles to Mongo beside `EDGARTOOLS_DECISION`.
- Treat MDM FastAPI graph JSON as the Agent Decision Surface (wrong store:
  Postgres mirror, no Decision Watermark / contract version).

---

## Answer

**No. MongoDB should not be the v1 Agent Decision Surface, instead of or
beside the Snowflake Decision Contract. A JSON document store should not
either.**

ADR 0001 currently locks: agents read **Snowflake only**; v1 delivery **is**
the Snowflake Decision Contract. CONTEXT, doctrine, and the product table
repeat that. This map's destination is the remaining Snowflake plan.

JSON already appears as the **nested Python payload** of
`build_issuer_subject_bundle` / `build_subject_feature_screen`. That is the
Decision Graph Bundle *shape*. It is not a Mongo collection and is not
persisted as agent SoE. Snowflake is defined to return that bundle **or
its relational equivalent**; SQL sketches are the relational equivalent
(still incomplete vs Python).

Mongo/JSON-store-as-plane would require a new ADR, new storage/secrets,
and would recreate the dual-truth failure ADR 0001 rejected. Gold, graph,
ingest, and SiS audit stay Snowflake regardless.

A later optional S3/API JSON **projection** of the published Snowflake
contract is already named in `docs/product-questions-and-dashboards.md`
("S3/API optional later"). Park it there. Do not expand this map.
