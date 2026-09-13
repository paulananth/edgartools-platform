# Route International Organizations through the common entity registry

Type: grilling
Status: resolved
Blocked by: 08

## Question

Does the GLEIF `INTERNATIONAL_ORGANIZATION` source category require a separate
MDM domain table and consumer?

## Answer

No. Include International Organization records in Release 1 through the common
MDM entity registry. Preserve `INTERNATIONAL_ORGANIZATION` as source-grained
GLEIF classification evidence, together with its names, addresses, legal form,
status, identifiers, lifecycle, and supported relationships. Do not add an
`mdm_international_organization` table or coerce the record into Company or
Government Entity.

GLEIF uses this category for a non-resident legal entity created by an
international agreement or similar arrangement. It is distinct from a resident
government body and from a private organization that merely operates in more
than one country. GLEIF does not define a separate non-governmental-organization
entity category; those records normally remain general legal-entity evidence.

The shared-foundation specification must define the generic legal-entity
registry representation, source-classification history, relationship routing,
export, API, stewardship, graph, checkpoint, and verification contracts. A
future dedicated domain is allowed only after a real consumer requires fields
or behavior that the common entity representation cannot support.

Accepted by the user during the 2026-09-13 Wayfinder session.
