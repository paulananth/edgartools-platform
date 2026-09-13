# International-organization common-entity route

Classification: mandatory source-classification route
Status: boundary accepted; implementation planned in shared foundation
Depends on: shared foundation generic legal-entity representation
Future spec: owned by `docs/specs/mdm-enrichment/shared-foundation.md`

## Destination

Route `INTERNATIONAL_ORGANIZATION` evidence through the common MDM entity
registry and preserve GLEIF identity, source classification,
jurisdiction/formation basis, lifecycle, and typed relationships without
coercing the entity into Company or Government Entity.

Do not add an `mdm_international_organization` table or a dedicated domain
consumer solely because GLEIF exposes this source category. The shared
foundation spec must define the generic registry representation, authoritative
corroboration, local identity acceptance, unsupported relationship endpoints,
and downstream use. A later dedicated domain requires a demonstrated consumer
need that the common representation cannot meet.
