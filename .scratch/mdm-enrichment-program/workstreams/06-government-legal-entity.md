# Government legal-entity enrichment

Classification: mandatory consumer
Status: planned
Depends on: shared foundation; explicit Government Entity domain
Future spec: `docs/specs/mdm-enrichment/government-entity.md`

## Destination

Route `RESIDENT_GOVERNMENT_ENTITY` and accepted related mapping evidence to a
Government Entity consumer without classifying it as Company. Preserve legal
jurisdiction, registration, lifecycle, and relationships at source grain.

Use the current separate-domain MDM pattern: add `government_entity` to
`mdm_entity` and store the projection in `mdm_government_entity`. LEI and
accepted QCC/GEM mappings remain source references and do not replace an
authoritative government identifier or prove ownership. The spec must define
fields, identity and uniqueness, QCC/GEM applicability, lifecycle,
relationships, privacy/security, and complete downstream publication.
