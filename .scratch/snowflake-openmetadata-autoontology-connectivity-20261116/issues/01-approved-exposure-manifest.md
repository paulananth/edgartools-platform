# Define the approved Snowflake exposure manifest

Status: open
Owner: Claude (operator, 2026-11-17: "take over Unresolved integration and safety gaps remain documented in docs/handoff-connectivity-claude.md"; the handoff's findings are the parts below).
Type: task

## Question

Implement the canonical, versioned manifest generated from repository rules that declares the Snowflake databases, schemas, tables, columns, descriptions, source-of-truth classification, and lineage references approved for AutoOntology and OpenMetadata exposure.

Acceptance criteria:

- One generated artifact has a stable schema and version/digest.
- Physical Snowflake identity is distinct from business meaning and authority.
- Scope excludes unapproved, staging, control, and internal tables.
- The artifact is deterministic and testable without credentials.
- Consumers can reject stale or incompatible manifest versions.

Blocked by: none

## Checklist

- [x] The code lives in a skill as generic scripts (operator, 2026-11-17: "only skills and generic scripts"; "Yes, move it all to skills (Recommended)"): `skills/data-platform/scripts/exposure/exposure_manifest.py`, moved unchanged with its tests, package entries removed (2026-11-17 19:59 ET; 16 tests passed from the new place)
- [x] The scope is decided (operator, 2026-11-17: "Silver, MDM and RDM"; then "Published-only RDM tables (Recommended)"): the 16 registered silver tables and MDM's two final tables, `mastering_master` (golden records, with merged-away ids as alias rows) and `mastering_identifier`; RDM waits for published-only tables (ticket 06) (2026-11-17 19:59 ET)
- [ ] A reviewed exposure list, `rules/exposure.yaml`, is the approval; a valid digest is not. No database or schema name hard-coded in the script (today `EDGARTOOLS_PROD`, `EDGARTOOLS_GOLD`, `EDGARTOOLS_SILVER`, which the rebuild does not build)
- [ ] The manifest is generated from that list and the tables themselves: each table's real columns, types and comments read back from its PostgreSQL store, not caller-created mappings
- [ ] A strict consumer schema (exact keys and types at every level), and freshness: the manifest binds the digest of the files it was made from, and a consumer refuses one they no longer make
- [ ] Identities held as parts (database, schema, table), never one dotted string; quoted names round-trip
- [ ] The Snowflake identity is the mirror's documented naming (`DB_EDGARTOOLS_MIRROR.<SCHEMA>.<TABLE>`, upper-cased) and marked unverified until the mirror is qualified
- [ ] Tests on invented tables in a disposable PostgreSQL: columns match the store, an unlisted table is absent, a table not in the store is refused, a changed list makes the old manifest stale
- [ ] Learning → skill
