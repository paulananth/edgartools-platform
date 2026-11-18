# Publish the approved Snowflake surface to OpenMetadata

Status: resolved
Owner: Claude (operator, 2026-11-17: "take over Unresolved integration and safety gaps remain documented in docs/handoff-connectivity-claude.md"; the handoff's findings are the parts below).
Type: task

## Question

Implement publication of the approved exposure manifest from `Define the approved Snowflake exposure manifest` into OpenMetadata, preserving repository rules as the business-definition authority and representing Snowflake physical assets, glossary terms, certifications, and lineage without inventing relationships.

Acceptance criteria:

- Publication is idempotent and scoped to manifest-owned assets.
- Snowflake database/schema/table/column identities match the manifest.
- Descriptions, glossary terms, certifications, and lineage use existing repository publisher conventions.
- Unsupported or unverified relationships are not published.
- Readback verifies asset scope, lineage, and metadata on the configured OpenMetadata version.

Blocked by: 01

## Checklist

- [x] Moved into `skills/data-platform/scripts/exposure/exposure_publish.py`, unchanged at the move, then rewritten here for the owned service (2026-11-17 19:59 ET)
- [x] No glossary term is published: the plan has none, and a unit test refuses one (2026-11-17 20:34 ET)
- [x] Exposure eligibility is its own classification tag, `exposure.approved`, owned by this publication; the tag's usage count equals the manifest's table count on readback (2026-11-17 20:34 ET; local OpenMetadata 2.0.7, 18 tables and 15 lineage links published and read back in 11 s)
- [x] A table's data class follows its layer and an unknown layer is refused; there is no source layer to tag; the two owned classifications' tags are set exactly, so a removed one does not linger, and any other tag (a steward's) is kept (2026-11-17 20:34 ET; unit tests; live: a `PII.None` tag survived a republish)
- [x] The shared `data_class` classification is never written: its tags are required to exist and only set on the service's own tables (2026-11-17 20:34 ET)
- [x] Identities stay as parts and go through `catalog.fqn`, which quotes a dotted part (2026-11-17 20:34 ET)
- [x] Each PostgreSQL type is translated to OpenMetadata's (length kept for CHAR and VARCHAR) and kept as written in `dataTypeDisplay`; a type with no mapping is refused (2026-11-17 20:34 ET; unit tests over every type the manifest holds)
- [x] Only the manifest's stated lineage is published; a reference to a table it does not hold is refused (2026-11-17 20:34 ET; live: 15 links read back)
- [x] No certification is published (the manifest names none). Idempotent means a repeat publish changes no table's version (2026-11-17 20:34 ET; live: republish set no tag, removed nothing, changed 0 of 18 versions)
- [x] The custom fake is gone: unit tests cover the plan only, and the readback is the live proof on the local server: publish, republish unchanged, a dropped table deleted (17 verified), restored (18) (2026-11-17 20:34 ET)
- [x] The local server's saved token had expired (HTTP 401): the proof logged in with the saved login and kept the session token in memory, writing nothing to the private file; `infra/openmetadata/init.sh` was not run, since it targets another instance and clears AI Governance resources (2026-11-17 20:34 ET)
- [x] Review findings fixed: the owned-tag rule is `retagged()` with a test keeping a steward's tag; a varchar with no length is TEXT, not length 1; a readback on an unqualified version is refused; a table naming itself as lineage is refused by the manifest; the unused version reader removed (2026-11-17 20:37 ET; tests/unit/test_exposure_publish.py, test_exposure_manifest.py)
- [x] Learning → skill: the exposure README's publication section: how to run it, what it owns, and that an expired token answers 401 on everything but `/system/version` (2026-11-17 20:34 ET)
