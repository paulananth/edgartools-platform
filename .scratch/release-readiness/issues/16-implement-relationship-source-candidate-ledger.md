# Implement Relationship Source Candidate Ledger

Type: task
Status: resolved
Blocked by: none
Blocks: 17, 18, 19

## Task

Implement the frozen proxy, Item 5.02, ambiguous-8-K, and 13F accession inventories plus the generation-bound Bulk-Load Completion Ledger defined by the Required Relationship Bulk-Load Completion Gate.

## Done when

- Missing SEC quarters or submission manifests fail closed.
- Every candidate has one accession-level outcome and evidence fingerprint.
- Ledger reconciliation detects missing, duplicate, unresolved, quarantined, or stale rows.
- Unit and architecture tests cover deterministic inventory and terminal-state rules.

## Resolution

Implemented by commit `1841e2f` in `edgar_warehouse.application.relationship_bulk_load`, with deterministic inventory fingerprints, missing-quarter/submission-manifest failure, duplicate detection, generation binding, terminal-state enforcement, and stale-evidence rejection.
