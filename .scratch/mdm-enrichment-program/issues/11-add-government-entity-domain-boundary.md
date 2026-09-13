# Add the Government Entity domain boundary

Type: grilling
Status: resolved
Blocked by: 08

## Question

Should GLEIF Government Entity evidence be stored as Company data or receive a
separate domain identity under the current MDM model?

## Answer

Add `government_entity` as its own `mdm_entity.entity_type` and add an
`mdm_government_entity` domain table keyed by that entity ID. Do not store a
Government Entity as a Company and do not reuse a Company, Adviser, or other
domain ID.

GLEIF is authoritative only for the legal-entity evidence it publishes. LEI,
QCC, and GEM identifiers attach as source-grained references only after the
Government Entity identity and mapping semantics are accepted. They do not
replace an authoritative government identifier or prove ownership. Applicable
relationships retain their source direction, time, and endpoint evidence;
unaccepted endpoints remain Deferred Domain Evidence.

The future specification must define the Government Entity fields, identifier
authority, uniqueness, lifecycle, cross-domain relationships, privacy/security,
resolver, export, Snowflake mirror, API, stewardship, graph, checkpoint, and
verification contracts.

Accepted by the user during the 2026-09-13 Wayfinder session.
