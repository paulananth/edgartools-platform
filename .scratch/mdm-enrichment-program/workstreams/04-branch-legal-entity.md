# Branch legal-entity enrichment

Classification: mandatory consumer
Status: planned
Depends on: shared foundation; BIC mapping; explicit Branch domain
Future spec: `docs/specs/mdm-enrichment/branch.md`

## Destination

Represent a GLEIF international branch as a Branch and publish
`IS_INTERNATIONAL_BRANCH_OF` only to an accepted head-office legal entity. Do
not create a Company or generic entity merely to satisfy either endpoint.

Use the current separate-domain MDM pattern: add `branch` to `mdm_entity`, store
the domain projection in `mdm_branch`, and keep the head office under its own
accepted domain identity. The spec must define the Branch table fields,
head-office classification, BIC branch semantics, lifecycle, missing endpoints,
source-reference uniqueness, and complete export/API/stewardship/graph parity.
