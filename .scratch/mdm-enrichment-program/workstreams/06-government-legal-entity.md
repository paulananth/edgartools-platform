# Government legal-entity enrichment

Classification: mandatory consumer
Status: planned
Depends on: shared foundation; explicit Government Entity domain
Future spec: `docs/specs/mdm-enrichment/government-entity.md`

> **Re-audited 2026-09-19 against the legacy-decommission directive.** The
> domain decision stands; the mechanism named here (`mdm_entity`/`mdm_*`
> tables) is legacy MDM's and is superseded by Clean MDM's
> `mdm_v2.identity.kind = 'government'` + `mdm_v2.projection`. The consumer spec
> for this workstream targets `mdm_v2` only. See
> `docs/specs/mdm-enrichment/shared-foundation.md`, "Governing directive".

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
