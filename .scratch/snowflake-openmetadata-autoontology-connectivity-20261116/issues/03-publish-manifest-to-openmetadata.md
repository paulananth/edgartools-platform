# Publish the approved Snowflake surface to OpenMetadata

Status: open
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

- [x] Moved unchanged to `skills/data-platform/scripts/exposure/exposure_publish.py` (2026-11-17 19:59 ET)
- [ ] Glossary term identity is not in the manifest: publish no glossary terms (none invented from `mdm` or other authority labels)
- [ ] Exposure eligibility is its own classification tag, apart from certification, data class and layer (data-platform FINAL-TABLES.md)
- [ ] An unknown authority is refused, not dropped; silver and source keep separate tags; a removed authority's old tag is removed
- [ ] No write to the shared `data_class` beyond manifest-owned assets
- [ ] No identity joined or split on dots (quoted names break)
- [ ] Column types translated through the catalog's type mapping
- [ ] Reference membership is not verified lineage: publish only the manifest's stated lineage
- [ ] Repeated certification patches change timestamps: state what idempotent means and prove it
- [ ] Replace the custom fake (generic handlers before lineage handlers) with readback from the local OpenMetadata server
- [ ] Learning → skill
