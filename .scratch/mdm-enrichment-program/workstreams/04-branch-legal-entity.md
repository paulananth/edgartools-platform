# Branch legal-entity enrichment

Classification: mandatory consumer
Status: planned
Depends on: shared foundation; BIC mapping; explicit Branch domain
Future spec: `docs/specs/mdm-enrichment/branch.md`

## Destination

Represent a GLEIF international branch as a Branch and publish
`IS_INTERNATIONAL_BRANCH_OF` only to an accepted head-office legal entity. Do
not create a Company or generic entity merely to satisfy either endpoint.

The spec must define branch identity, head-office classification, BIC branch
semantics, lifecycle, missing endpoints, and graph parity.
