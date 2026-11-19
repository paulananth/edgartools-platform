# Connect AutoOntology to the approved Snowflake surface

Status: open
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
- [ ] The upstream structured Snowflake factory drops `role`: enforce the role another way, or say it is not enforceable
- [x] Table selection by exact identity: the catalog is read back after the connection is made and must equal the manifest's (schema, table) pairs, extras and missing refused (counts only); `tests/unit/test_autoontology_connection.py`, the first test failed when the comparison was removed. 2026-11-19 12:30 ET
- [x] The ingested identities are read back from the catalog whichever path filled it, so a scheduled ingestion that ignored the filter is refused. 2026-11-19 12:30 ET
- [x] The outcome is the contract's: not running, a success time, and no newer failure; the old `blockers` field does not exist upstream. Three of four new cases failed when the failure check was removed. 2026-11-19 12:30 ET
- [ ] `validate_query`'s live path raises an unimplemented-streaming error: implement the supported SSE query validation, never count an invented response as proof
- [x] The connection string's user and password are percent-decoded once; an error names the route and the counts only. 2026-11-19 12:30 ET
- [x] `Any` and `Callable` imported. 2026-11-19 12:30 ET
- [ ] ~~Generated SQL and rows on Snowflake~~ deferred to the mirror's qualification: no Snowflake surface exists yet; prove the same on the local PostgreSQL readers meanwhile
- [ ] Learning → skill
