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
- [ ] Read AutoOntology's contracts from the release in use (`~/projects/auto-ontology`, its commit named), never commit there
- [x] The PostgreSQL readers are proved on the exposure list: SELECT on exactly the listed tables by name, no schema-wide or default grant, zero write privileges, TLS; created live as `discovery_reader_mdm`, `_rdm` and `_silver` (readable: 2 + 1 + 16 listed tables, plus each database's extension views). 2026-11-19 12:40 ET
- [ ] A `_READER` suffix proves no grants on Snowflake: prove the Snowflake reader's effective SELECT-only, table-level grants against the manifest (needs the mirror)
- [ ] The upstream structured Snowflake factory drops `role`: enforce the role another way, or say it is not enforceable
- [ ] Table selection by exact identity, not an unqualified regex across schemas (name collisions)
- [ ] Scheduled ingestion may prefer `CONNECTION_STRINGS` over filtered UI connections: fail closed, and read the ingested identities back
- [ ] `calculated` alone is not compilation success: read the compilation's real outcome
- [ ] `validate_query`'s live path raises an unimplemented-streaming error: implement the supported SSE query validation, never count an invented response as proof
- [ ] URL credentials decoded correctly; exceptions never carry a secret
- [ ] `Any` and `Callable` are used but never imported (ruff F821)
- [ ] ~~Generated SQL and rows on Snowflake~~ deferred to the mirror's qualification: no Snowflake surface exists yet; prove the same on the local PostgreSQL readers meanwhile
- [ ] Learning → skill
