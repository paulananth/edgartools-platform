# Inventory JSON and MongoDB as an end-user agentic data plane

Type: research
Status: resolved
Blocked by: none

## Question

The operator asked whether JSON documents and/or MongoDB should be the
end-user Agent Decision Surface, instead of or beside the Snowflake
Decision Contract (ADR 0001: agents read Snowflake only; delivery is the
Snowflake Decision Contract).

Against in-repo ADRs, glossary, serving modules, and live architecture
(not vendor blogs), report:

1. What the current end-user agent read path actually is (Snowflake
   objects, Python bundle dicts, Streamlit, any JSON export).
2. Whether any MongoDB, document store, or JSON contract already exists
   in this repo or prod path.
3. What a Decision Graph Bundle already is as a document-shaped payload
   (`subject_bundle_read`, coverage flags, watermark) versus a Mongo
   collection.
4. What ADR 0001 / CONTEXT.md would have to change to make JSON or
   MongoDB the agent plane; what would stay Snowflake.
5. Fit with this map's destination (implementation-ready Snowflake
   Decision Contract plan) versus a later serving-layer effort.

Save findings at
`.scratch/agent-decision-contract/research/10-json-mongodb-agentic-data-plane.md`.
Cite file paths and ADRs. Do not implement. Do not treat vendor
MongoDB/JSON marketing as a source of truth for this platform.

## Answer

**No.** MongoDB should not be the v1 Agent Decision Surface, instead of or
beside Snowflake. A JSON document store should not either.

ADR 0001 currently locks agents to **Snowflake only**; v1 delivery **is**
the Snowflake Decision Contract. CONTEXT Agent SoE, doctrine, and the
product table (`S3/API optional later`) repeat that. This map's destination
is the remaining Snowflake plan.

JSON already exists as the nested Python payload of
`build_issuer_subject_bundle` / `build_subject_feature_screen` — that is the
Decision Graph Bundle *shape*, not a Mongo collection and not a persisted
agent SoE. No `pymongo`/Mongo/DocumentDB appears in `pyproject.toml`,
`uv.lock`, or Terraform. Live `EDGARTOOLS_DECISION` is still an empty
schema; Agent View reads Snowflake display views.

Mongo/JSON-store-as-plane would need a new ADR, a new storage target (this
map forbids that), and would recreate dual truth. Gold, graph, ingest, and
SiS audit stay Snowflake. Park any HTTPS/S3 JSON *projection* of the
published contract as a later serving-layer effort.

Findings:
[research/10-json-mongodb-agentic-data-plane.md](../research/10-json-mongodb-agentic-data-plane.md)
