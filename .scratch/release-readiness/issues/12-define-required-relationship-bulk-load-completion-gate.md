# Define Required Relationship Bulk-Load Completion Gate

Type: research
Status: resolved
Blocked by: none
Blocks: 06

## Question

What source inventory, load-completion evidence, derivation outputs, and replay rules prove that all required DEF 14A, 8-K, and 13F-HR inputs have been processed for `EMPLOYED_BY` and `INSTITUTIONAL_HOLDS` at the Release Data Watermark?

## Exit criteria

- Define the authoritative source-candidate inventory and watermark.
- Define load completeness, idempotency, retry, and repair evidence.
- Bind candidates to applicability-ledger outcomes and MDM versions.
- Define per-type MDM-to-hosted-Neo4j parity evidence.
- Assign implementation and release-acceptance owners.

## Answer

[Required Relationship Bulk-Load Completion Gate](../../../docs/release-readiness/required-relationship-bulk-load-completion-gate.md) defines a fail-closed, accession-level source inventory and completion ledger for Reported Executive Employment and Institutional Holdings. It uses a declared `2013-05-20` source-history boundary, current-state baselines, per-candidate terminal outcomes, no release-mode caps, bounded idempotent retry, explicit repair manifests, temporal/amendment semantics, and exact MDM-to-hosted-graph parity.

The current implementation cannot pass: Branch B forms are excluded from bulk artifact selection; Branch B failures and per-filing skips can continue silently; the 8-K path lacks Item 5.02 employment events; the 13F index builder can skip failed quarters; 13F manager and amendment semantics are incomplete; and existing operator scripts cap derivation/publication. Tasks 16–20 carry those implementation blockers.
