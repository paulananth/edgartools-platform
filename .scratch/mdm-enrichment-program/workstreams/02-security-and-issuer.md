# Security and issuer enrichment

Classification: mandatory consumer
Status: planned
Depends on: shared foundation; ISIN mapping
Future spec: `docs/specs/mdm-enrichment/security-issuer.md`

## Destination

Route accepted ISIN-to-LEI evidence to Security identifiers and typed issuer
relationships. An ISIN never becomes a Company attribute, and neither endpoint
publishes until the Security and issuing legal entity are independently accepted.

The spec must reconcile the existing `mdm_security.isin` and `ISSUED_BY`
contracts, define conflict/retirement behavior, and prove complete mapping-file
inventory, uniqueness, replay, and graph parity.
