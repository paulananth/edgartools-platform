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

## Comments

- 2026-09-19, decommission re-audit (Shared Foundation spec release gate 4):
  the **decision stands** — a Government Entity is its own identity, never stored as a Company. The **mechanism** named above
  (`mdm_entity.entity_type` plus a per-domain `mdm_government_entity` table) is legacy MDM's
  and is superseded: legacy MDM is being decommissioned, and Clean MDM's
  `mdm_v2.identity.kind` already admits `government` with the domain projection
  in `mdm_v2.projection`. No new table. See
  `docs/specs/mdm-enrichment/shared-foundation.md`, "Governing directive".
