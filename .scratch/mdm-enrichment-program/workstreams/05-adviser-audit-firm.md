# Adviser and audit-firm legal-entity enrichment

Classification: mandatory consumer
Status: planned
Depends on: shared foundation; legal-entity classification
Future spec: `docs/specs/mdm-enrichment/adviser-audit-firm.md`

## Destination

Bind accepted Adviser and Audit Firm identities to GLEIF evidence without
duplicating them as Companies or changing SEC/IAPD/PCAOB authority. Route BIC,
QCC, GEM, and relationship evidence only when their semantics apply.

The spec must define deterministic source links, cross-domain identity
constraints, field authority, conflicts, and whether a single legal entity may
have governed projections in more than one existing MDM domain.
