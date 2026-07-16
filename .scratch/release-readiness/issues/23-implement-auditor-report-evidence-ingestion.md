# Implement Auditor-Report Evidence Ingestion

Type: task
Status: resolved
Blocked by: 15, 16
Blocks: 20, 06

## Task

Implement the approved auditor-evidence contract: inventory every annual filing candidate, capture direct SEC evidence and PCAOB AuditorSearch/Form AP bulk data, parse the Inline XBRL auditor triplet or bounded audit-report/signature fallback, model the full PCAOB firm identity set, and derive report-date `AUDITED_BY` versions.

## Done when

- Every eligible annual filing/amendment and relevant SEC/PCAOB artifact is frozen with immutable hashes, source locators, schema/data-dictionary versions, and watermark identity.
- Append-only auditor-report evidence records the filing, audited period, report date, principal firm, normalized PCAOB Firm ID, evidence source, raw locator, amendment chain, and evidence fingerprint.
- The direct iXBRL parser validates the complete auditor triplet; the deterministic fallback is bounded to the independent-auditor report/signature and never uses unbounded fuzzy or LLM extraction.
- The full PCAOB identity/alias set replaces the current top-firm lookup; unknown valid Firm IDs create deterministic entities and ambiguous pre-tag aliases remain unresolved.
- Every candidate has one terminal outcome, base annual filings cannot be silently not applicable, and no unresolved/quarantined/exhausted-retry candidate remains.
- Temporal versions use the audit report date, replay idempotently, and exact MDM-to-hosted-graph endpoint, period, source, evidence, and temporal parity passes.
- Focused inventory, parser, identity, temporal, retry, repair, idempotency, and parity tests pass and their evidence is bound to the release candidate.

## Contract

[`docs/release-readiness/auditor-evidence-ingestion-contract.md`](../../../docs/release-readiness/auditor-evidence-ingestion-contract.md)

## Resolution

Implemented by commits `ddc24d3`, `846d648`, and `4f4e1a9`: direct annual-filing iXBRL triplets
are validated fail-closed, the fallback is bounded to the independent-auditor report
and signature, append-only evidence and the full PCAOB snapshot are stored with
hashes, and valid long-tail PCAOB IDs create deterministic audit-firm entities.
`AUDITED_BY` now uses the report date and evidence fingerprint. Production candidate
closure, Form AP corroboration timing, and hosted-graph parity remain ticket 20
execution evidence.
