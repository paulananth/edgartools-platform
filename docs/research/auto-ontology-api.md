# NVIDIA AutoOntology API: integration research

**Source checked:** [`NVIDIA/auto-ontology`](https://github.com/NVIDIA/auto-ontology), branch `main`, 2026-11-14. This is source/documentation research only; no instance was installed or contacted. `main` is not a release pin, so verify the selected release's own OpenAPI and skills before implementation.

## Recommendation for EdgarTools

Use AutoOntology as a **read-only semantic query layer** over separately authorized MDM, RDM, and Silver sources. Preserve the platform's single authority per fact: MDM owns mastered identities/relationships, RDM owns approved code sets, Silver owns transaction facts, and repository Rules/`CONTEXT.md` own definitions and processing policy. Leave the existing Rules → OpenMetadata publication path unchanged. Do not treat AutoOntology's ontology database as a copy of those systems of record or publish its edits directly into Rules/OpenMetadata. See the platform's [data-catalog contract](../../skills/data-catalog/SKILL.md), [OpenMetadata contract](../../skills/openmetadata/SKILL.md), and [NVIDIA AutoOntology overview](https://github.com/NVIDIA/auto-ontology#how-it-works).

## API boundary

The consumer contract is the generated [`docs/openapi/auto-ontology-api.json`](https://github.com/NVIDIA/auto-ontology/blob/main/docs/openapi/auto-ontology-api.json), served by the **Next.js web application**. The OpenAPI README says the backend and ingestion FastAPI specs describe ClusterIP-only internal services; consumers should call the public gateway, not ports `3001`/`3002`. The public spec carries per-operation permission, source-route, and proxy metadata; it has no `servers` block, so the host must come from the selected deployment. See the [OpenAPI README](https://github.com/NVIDIA/auto-ontology/blob/main/docs/openapi/README.md).

| Use | Public API / permission | Contract and integration consequence |
|---|---|---|
| Check/add a data connection | `POST /api/connections/test` and `POST /api/connections` — `connection:manage`; `GET /api/connections` — `connection:read` | A test validates credentials and returns schemas; creating a connection stores it and triggers ingestion best-effort. Verify ingestion separately. UI-managed connections supersede `CONNECTION_STRINGS`. The [connection routes](https://github.com/NVIDIA/auto-ontology/blob/main/frontend/app/api/connections/route.ts) enforce permissions. |
| Discover meaning | `GET /api/terms`, `GET /api/terms/{term_id}`, `GET /api/exploration/tables/{table_id}/details` — `catalog:read` | Terms, mapped columns, relationships, and SQL attributes are semantic-layer reads, not a raw database browser. |
| Check and ask | `POST /api/question-entity-coverage` — `chat:use`; `POST /api/chat/completions` — `chat:use` | The chat endpoint streams SSE and returns generated SQL and rows; results are capped at 100 rows with truncation metadata. Validate SQL, row scope, and the answer before making a claim. |
| Readiness | `GET /api/semantic-compilation/status` — `chat:use`; MCP `check_readiness` | Readiness requires both compiled semantics and a live source connection. A non-empty catalog or compiled layer alone does not prove SQL can execute. |
| Edit semantic definitions | `PATCH /api/terms/{term_id}`, column/SQL-attribute routes — `catalog:edit` | REST is not read-only. Writes alter AutoOntology's semantic model; there is no public create-empty-term POST. Treat edits as proposals, not platform-authoritative changes. |
| Import/export model | `POST /api/model/export` — `modelInterchange:export`; `POST /api/model/import` — `modelInterchange:import` | Export can scope database IDs. Import's `replace` defaults to `true`; take a scoped backup, use an isolated target, and compare exact re-export before considering it successful. |
| Reset compiled layer | `POST /api/semantic-compilation/reset` — `semanticCompilation:manage` | Destructive and asynchronous; deletes/rebuilds compiled state across databases. It is not a routine cleanup or a source-store reset. |

The route inventory is larger than the agent interface: `docs/mcp.md` and the MCP tool source describe 87 public OpenAPI operations. The MCP server intentionally exposes a small allow-list of semantic reads and query tools; unspecified routes are excluded, and the tools do not modify the catalog or underlying databases. See [MCP docs](https://github.com/NVIDIA/auto-ontology/blob/main/docs/mcp.md) and the [`tools.py` allow-list](https://github.com/NVIDIA/auto-ontology/blob/main/mcp/auto_ontology_mcp/tools.py).
REST authentication supports browser sessions, API tokens, OAuth, and SSO according to the selected deployment. API tokens act as their owner; route permissions still apply. MCP uses user OAuth sign-in and holds no token of its own. Keep FastAPI (`:3001`) and ingestion (`:3002`) internal; public clients use the Next.js web origin. See the [query skill](https://github.com/NVIDIA/auto-ontology/blob/main/skills/nvidia-ontology-query/SKILL.md), [MCP docs](https://github.com/NVIDIA/auto-ontology/blob/main/docs/mcp.md), and [OpenAPI README](https://github.com/NVIDIA/auto-ontology/blob/main/docs/openapi/README.md).
Prefer MCP for agent query/read use; use REST only for a separately authorized administrative workflow.

## Source ingestion and data-scope risks

- AutoOntology's documented ingestion extracts relational schemas, columns, views, keys, foreign keys, query metadata, and may profile/sample values; it builds terms, relationships, SQL attributes, and embeddings in its own Postgres-backed semantic/catalog store. Query execution then uses the configured source connection. See the [upstream overview](https://github.com/NVIDIA/auto-ontology#how-it-works) and [`catalog/extract.py`](https://github.com/NVIDIA/auto-ontology/blob/main/auto_ontology/catalog/extract.py).
- The setup skill documents schema allowlists and table allow/deny regexes for UI-managed connections. It also says environment `CONNECTION_STRINGS` has no table filters and the full table-level scope guarantee is not yet established ([setup skill](https://github.com/NVIDIA/auto-ontology/blob/main/skills/nvidia-ontology-setup/SKILL.md), [issue #255](https://github.com/NVIDIA/auto-ontology/issues/255)). If a table or field must never be sampled or embedded, do not connect a real store until the exact pinned release proves that restriction end-to-end.
- Give each MDM/RDM/Silver source a dedicated `SELECT`-only identity scoped to approved schemas/tables. Do not reuse this platform's runtime, migration, or owner credentials; see [connection duty guidance](../../skills/data-platform/CONNECTIONS.md).
- Verify whether sample values or prompts are sent to configured NVIDIA NIM endpoints, and obtain approval before any external inference request. Start with invented/sanitized test data. AutoOntology's application/ontology/vector storage must remain separate from MDM, RDM, Silver, and OpenMetadata storage.

## Suggested integration sequence

1. Pin the AutoOntology release/chart and read its matching public OpenAPI, MCP, and setup contracts.
2. Prove source-table and sample-value scope on a disposable database using read-only credentials; no platform or provider data in the first test.
3. Add only approved MDM, RDM, and Silver connections. Verify source inventory, compiled semantic readiness, and a positive plus unsupported question; inspect generated SQL and returned rows.
4. Keep MCP to the supported read-only allow-list. Keep `connection:manage`, `catalog:edit`, model import, and compilation reset out of ordinary query clients.
5. Keep OpenMetadata as the existing Rules-derived catalog. If an approved AutoOntology definition should become canonical, review it into its owning repository Rules first, then use the existing publisher; there is no documented direct AutoOntology → OpenMetadata synchronization contract.

## Primary sources

- [Public OpenAPI spec](https://github.com/NVIDIA/auto-ontology/blob/main/docs/openapi/auto-ontology-api.json) and [spec-generation/consumer guidance](https://github.com/NVIDIA/auto-ontology/blob/main/docs/openapi/README.md)
- [MCP protocol, auth, and read-only tools](https://github.com/NVIDIA/auto-ontology/blob/main/docs/mcp.md)
- [Management/write API index](https://github.com/NVIDIA/auto-ontology/blob/main/skills/nvidia-ontology-management/references/write-api.md)
- [Setup, connections, and scope limits](https://github.com/NVIDIA/auto-ontology/blob/main/skills/nvidia-ontology-setup/SKILL.md)
- [Query validation guidance](https://github.com/NVIDIA/auto-ontology/blob/main/skills/nvidia-ontology-query/SKILL.md)
- [Connection authorization routes](https://github.com/NVIDIA/auto-ontology/blob/main/frontend/app/api/connections/route.ts) and [schema extraction](https://github.com/NVIDIA/auto-ontology/blob/main/auto_ontology/catalog/extract.py)
