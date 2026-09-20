# Branch legal-entity enrichment

Classification: mandatory consumer
Status: planned
Depends on: shared foundation; BIC mapping; explicit Branch domain
Future spec: `docs/specs/mdm-enrichment/branch.md`

> **Re-audited 2026-09-19 against the legacy-decommission directive.** The
> domain decision stands; the mechanism named here (`mdm_entity`/`mdm_*`
> tables) is legacy MDM's and is superseded by Clean MDM's
> `mdm_v2.identity.kind = 'branch'` + `mdm_v2.projection`. The consumer spec
> for this workstream targets `mdm_v2` only. See
> `docs/specs/mdm-enrichment/shared-foundation.md`, "Governing directive".

## Destination

Represent a GLEIF international branch as a Branch and publish
`IS_INTERNATIONAL_BRANCH_OF` only to an accepted head-office legal entity. Do
not create a Company or generic entity merely to satisfy either endpoint.

Use the current separate-domain MDM pattern: add `branch` to `mdm_entity`, store
the domain projection in `mdm_branch`, and keep the head office under its own
accepted domain identity. The spec must define the Branch table fields,
head-office classification, BIC branch semantics, lifecycle, missing endpoints,
source-reference uniqueness, and complete export/API/stewardship/graph parity.
