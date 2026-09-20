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

## Comments

- 2026-09-19, decommission re-audit (Shared Foundation spec release gate 4):
  the **decision stands** — a Branch is its own identity, never a Company/Adviser/head-office ID. The **mechanism** named above
  (`mdm_entity.entity_type` plus a per-domain `mdm_branch` table) is legacy MDM's
  and is superseded: legacy MDM is being decommissioned, and Clean MDM's
  `mdm_v2.identity.kind` already admits `branch` with the domain projection
  in `mdm_v2.projection`. No new table. See
  `docs/specs/mdm-enrichment/shared-foundation.md`, "Governing directive".
