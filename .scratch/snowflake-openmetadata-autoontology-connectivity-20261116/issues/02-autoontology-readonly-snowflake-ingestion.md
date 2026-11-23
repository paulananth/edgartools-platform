# Connect AutoOntology to the approved Snowflake surface

Status: claimed
Owner: Claude (operator, 2026-11-17: "take over Unresolved integration and safety gaps remain documented in docs/handoff-connectivity-claude.md"; the handoff's findings are the parts below).
Type: task

## Question

Implement a read-only AutoOntology Snowflake connection using the approved exposure manifest from `Define the approved Snowflake exposure manifest`. Ingest only the approved schemas and tables, compile the semantic layer, and validate generated SQL and result readback.

Acceptance criteria:

- Authentication uses private environment or secret storage, never command arguments or committed files.
- The Snowflake role is read-only and limited to the approved database/schema/table scope.
- AutoOntology ingestion is bounded by the manifest and does not silently fall back to the full database.
- Semantic compilation reports no unresolved source or scope blockers.
- At least one synthetic or approved test query is validated against generated SQL and rows.

Blocked by: 01

## Checklist

- [x] Moved unchanged to `skills/data-platform/scripts/exposure/autoontology.py` (2026-11-17 19:59 ET)
- [x] Read AutoOntology's contracts from the release in use (`~/projects/auto-ontology` at commit 8ff3060): the table filter matches the unqualified relation name, case-sensitive; `GET /api/schemas/{db}` and `GET /api/tables/{schema_id}` list what was ingested; `/api/semantic-compilation/status` returns calculated, running, last_success_at and last_failure_at (there is no `blockers` field). Nothing committed there. 2026-11-19 12:30 ET
- [x] The PostgreSQL readers are proved on the exposure list: SELECT on exactly the listed tables by name, no schema-wide or default grant, zero write privileges, TLS; created live as `discovery_reader_mdm`, `_rdm` and `_silver` (readable: 2 + 1 + 16 listed tables, plus each database's extension views). 2026-11-19 12:40 ET
- [ ] A `_READER` suffix proves no grants on Snowflake: prove the Snowflake reader's effective SELECT-only, table-level grants against the manifest (needs the mirror)
- [ ] AutoOntology's structured Snowflake connection factory drops the `role` payload (`auto_ontology/connectors/connection_string_factory.py:75-95`); its connector only applies a role parsed from the URL query (`snowflake.py:157-159`). This client path cannot enforce the requested role until upstream carries it through or a verified default-role/grant boundary replaces it.
- [x] Table selection by exact identity: the catalog is read back after the connection is made and must equal the manifest's (schema, table) pairs, extras and missing refused (counts only); `tests/unit/test_autoontology_connection.py`, the first test failed when the comparison was removed. 2026-11-19 12:30 ET
- [x] The ingested identities are read back from the catalog whichever path filled it, so a scheduled ingestion that ignored the filter is refused. 2026-11-19 12:30 ET
- [x] The outcome is the contract's: not running, a success time, and no newer failure; the old `blockers` field does not exist upstream. Three of four new cases failed when the failure check was removed. 2026-11-19 12:30 ET
- [x] Implemented the query-validation client path through the documented `POST /api/chat/completions` SSE stream, comparing generated SQL and rows; unit tests verify request, result parsing and `[DONE]` handling only, not a live generated query (2026-11-22).
- [x] The connection string's user and password are percent-decoded once; an error names the route and the counts only. 2026-11-19 12:30 ET
- [x] `Any` and `Callable` imported. 2026-11-19 12:30 ET
- [ ] Qualify generated SQL and returned rows on the approved Snowflake mirror after it exists and the exact target, credentials and authorization are approved; no live query was attempted. The synthetic stream test is client-contract evidence only.
- [x] Learning → skill: documented the SSE endpoint and that fixture results are not live qualification evidence (2026-11-22).
