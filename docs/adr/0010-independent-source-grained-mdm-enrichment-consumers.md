# Use source-grained evidence and independently releasable MDM enrichment consumers

Status: accepted

External enrichment sources such as GLEIF span several entity, identifier, and
relationship domains whose meanings and authorities differ. Capture each source
publication once as source-grained evidence, but publish it only through an
explicit MDM domain consumer with independent identity, temporal, replay,
rollback, observability, and release gates. Shared capture is not publication
authority, and unsupported records remain deferred evidence rather than being
coerced into Company or a generic entity.

## Considered options

- One enrichment pipeline that publishes every captured record was rejected
  because source availability does not prove local identity or domain semantics.
- Separate source downloads per MDM domain were rejected because they duplicate
  cost and can observe inconsistent publications.
- A generic legal-entity consumer was rejected because it would erase material
  distinctions among Company, Fund, Branch, government entity, international
  organization, sole proprietor, Adviser, Audit Firm, and Market/Venue.

## Consequences

Each consumer can ship and roll back independently, but the platform must keep
explicit deferred-domain and stewardship states. New sources require an
authority and licensing decision, and changing one consumer cannot silently
change another consumer's publication contract.
