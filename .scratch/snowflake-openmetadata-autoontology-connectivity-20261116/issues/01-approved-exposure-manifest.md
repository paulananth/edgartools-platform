# Define the approved Snowflake exposure manifest

Status: resolved
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
- [x] A reviewed exposure list, `rules/exposure.yaml`, is the approval, with the operator's words; a valid digest is not. The script names no table, schema or database (2026-11-17 20:13 ET; unit tests build only from an invented list)
- [x] The manifest is generated from that list and the tables themselves, read back from each PostgreSQL store (2026-11-17 20:13 ET; on a fresh disposable store with every silver spec registered by the writer and MDM migrated: 18 tables, 235 columns, every silver table's columns equal to the writer's, 15 silver tables with lineage to the golden records)
- [x] A strict consumer schema (exact keys at every level), and freshness: the manifest binds its list's digest and `check` refuses one the list no longer makes (2026-11-17 20:13 ET; unit tests)
- [x] Identities held as parts, never one dotted string; a name with a dot, quote or space is refused rather than quoted (2026-11-17 20:13 ET; unit test). `exposure_parity.py` joined every physical value including `verified`: it now joins the three parts
- [x] The Snowflake identity is the mirror's documented naming (`DB_EDGARTOOLS_MIRROR.<SCHEMA>.<TABLE>`, upper-cased), `verified: false` until the mirror is qualified (2026-11-17 20:13 ET)
- [x] Tests: 18 unit (`tests/unit/test_exposure_manifest.py`) and 3 on a real PostgreSQL (`tests/integration/test_exposure_manifest_postgres.py`): columns, types and comments from the store, an unlisted table absent, a missing table refused, an unset or unreachable store named by its setting with no address (2026-11-17 20:13 ET)
- [x] Problem found while proving: a debugging print of a driver error showed a disposable store's connection string. Root cause: psycopg puts the address in its error text. Fix: the script reports only the error's class, and a test proves the password is absent; the store (`ipo2`, a throwaway from the IPO proof, stopped hours before) was deleted with its volume and env files (2026-11-17 20:13 ET)
- [x] Learning → skill: the exposure README (`skills/data-platform/scripts/exposure/README.md`): how to generate and check, what is refused, and that a driver error can carry the address so only its class is reported (2026-11-17 20:13 ET)
