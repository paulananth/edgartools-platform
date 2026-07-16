# Define Relationship Eligibility at the Release Watermark

Type: grilling
Status: resolved
Blocked by:

## Question

Which relationship records are active and in scope at the release watermark, how are exclusions represented, and what per-type MDM-to-hosted-graph parity evidence constitutes Hosted Graph Completeness?
## Resolution

Resolved by [Relationship Eligibility at the Release Watermark](../../../docs/release-readiness/relationship-eligibility-at-release-watermark.md).

All eleven registered relationship types are required for initial GO, while individual relationships remain optional per entity through a complete applicability ledger. Eligibility, coverage, and exact MDM-to-hosted-Neo4j parity derive from one transaction-consistent generation snapshot at the Release Data Watermark. GO permits no excluded types, unresolved or missing candidates, unproven zero classifications, or parity mismatches.

This decision exposes separate hard blockers for bulk-source completion, adviser/fund data, parent-company parsing, and auditor-evidence ingestion.
