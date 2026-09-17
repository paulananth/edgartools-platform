# Add the Branch domain boundary

Type: grilling
Status: resolved
Blocked by: 08

## Question

How should a GLEIF international branch fit the current MDM model, which uses
one typed registry identity plus one separate table for each supported domain?

## Answer

Add `branch` as its own `mdm_entity.entity_type` and add an `mdm_branch` domain
table keyed by that Branch `entity_id`. A Branch does not reuse a Company,
Adviser, or head-office entity ID and is not coerced into any of those domains.

Connect an accepted Branch to its separately accepted head-office legal entity
with the directional `IS_INTERNATIONAL_BRANCH_OF` relationship. Preserve GLEIF
source direction and temporal evidence. Missing or unaccepted endpoints remain
Deferred Domain Evidence and do not cause creation of a generic or placeholder
entity.

The future specification must extend the hard-coded entity-type constraint,
entity-type registry, resolver, source-reference uniqueness, export, Snowflake
mirror, API, stewardship, graph, checkpoint, and verification surfaces. This is
an extension of the current separate-domain model, not a multi-role identity
redesign.

Accepted by the user during the 2026-09-13 Wayfinder session.
