# Implement SEC Subsidiary Exhibit Ingestion

Type: task
Status: open
Blocked by: 14, 16
Blocks: 20, 06

## Task

Implement the approved parent-company contract: enumerate complete annual-filing attachment and incorporated-reference candidates, parse domestic Exhibit 21 and Form 20-F Exhibit 8 artifacts, resolve non-CIK legal-company identities, and derive evidence-bound `HAS_PARENT_COMPANY` versions with `parent_scope=registrant_disclosed`.

## Done when

- Complete submissions history, eligible annual filings/amendments, attachment indexes, incorporated references, source bytes, and candidate rows are frozen at the release watermark.
- Deterministic HTML/text/PDF adapters preserve row locators, raw names, jurisdiction, DBA/footnote/omission evidence, hashes, and parser versions; unsupported artifacts fail closed.
- No indentation or table order is treated as immediate legal hierarchy, and unsupported Form 40-F coverage remains unresolved rather than silently not applicable.
- Deterministic non-CIK company identities are supported without manufactured CIKs; fuzzy matches never auto-accept.
- Every candidate has one terminal outcome, explicit-zero evidence is distinguished from missing exhibits, and no unresolved/quarantined/exhausted-retry candidate remains.
- Temporal versions replay idempotently and exact MDM-to-hosted-graph endpoint, scope, source, evidence, and temporal parity passes.
- Focused inventory, parser, identity, temporal, retry, idempotency, and parity tests pass and their evidence is bound to the release candidate.

## Contract

[`docs/release-readiness/parent-company-source-parser-contract.md`](../../../docs/release-readiness/parent-company-source-parser-contract.md)
