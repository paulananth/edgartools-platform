# Define Auditor Evidence Ingestion Contract

- Type: research
- Status: resolved
- Blocked by: none
- Blocks: 23

## Question

Which authoritative filing evidence and ingestion method will support complete `AUDITED_BY` candidate enumeration and derivation when the current company-facts path lacks the required evidence?

## Exit criteria

- Select the authoritative filing/evidence source and acquisition method.
- Define candidate enumeration, parser, provenance, and auditor identity rules.
- Define not-applicable, unresolved, quarantine, retry, and repair behavior.
- Bind derivation to applicability and per-type parity evidence.
- Assign implementation and release-acceptance owners.

## Resolution

Approved direct annual-filing evidence as primary: the filing's complete Inline XBRL auditor triplet when valid, otherwise a bounded independent-auditor-report/signature parser. PCAOB AuditorSearch/Form AP bulk data supplies the canonical firm identity, amendments, and corroboration. The contract defines candidate inventory, append-only evidence, report-date temporal semantics, terminal outcomes, repair, and exact MDM/graph parity.

Decision artifact: [`docs/release-readiness/auditor-evidence-ingestion-contract.md`](../../../docs/release-readiness/auditor-evidence-ingestion-contract.md)

Implementation remains required under ticket 23; resolving this research ticket does not make `AUDITED_BY` launch-ready.
