# Security and issuer enrichment

Classification: mandatory consumer
Status: planned
Depends on: shared foundation; ISIN mapping
Future spec: `docs/specs/mdm-enrichment/security-issuer.md`

> **Re-audited 2026-09-19 against the legacy-decommission directive.** The
> domain decision stands; the mechanism named here (`mdm_entity`/`mdm_*`
> tables, `mdm_security.isin`, `ISSUED_BY`) is legacy MDM's and is superseded by Clean MDM's
> `mdm_v2.identity.kind = 'security'` + `mdm_v2.projection`. The consumer spec
> for this workstream targets `mdm_v2` only. See
> `docs/specs/mdm-enrichment/shared-foundation.md`, "Governing directive".

## Destination

Route accepted ISIN-to-LEI evidence to Security identifiers and typed issuer
relationships. An ISIN never becomes a Company attribute, and neither endpoint
publishes until the Security and issuing legal entity are independently accepted.

The spec must reconcile the existing `mdm_security.isin` and `ISSUED_BY`
contracts, define conflict/retirement behavior, and prove complete mapping-file
inventory, uniqueness, replay, and graph parity.
