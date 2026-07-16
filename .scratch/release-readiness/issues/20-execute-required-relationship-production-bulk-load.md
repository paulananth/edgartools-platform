# Execute Required Relationship Production Bulk Load

Type: task
Status: open
Blocked by: 17, 18, 19
Blocks: 06

## Task

Run the strict production bulk load at the frozen Release Data Watermark, repair every unresolved candidate, derive both relationship types without caps, publish the graph generation, and commit the passing evidence artifact.

## Done when

- Candidate inventory and Bulk-Load Completion Ledger reconcile exactly.
- Failure, unresolved, quarantine, circuit-breaker-leftover, and unapproved-force counts are zero.
- A no-change rerun makes no SEC requests and produces identical silver/MDM semantic digests with zero new relationship identities.
- `EMPLOYED_BY` and `INSTITUTIONAL_HOLDS` pass exact MDM-to-hosted-graph parity and current-at-watermark checks.
- Named Warehouse, MDM, Graph, Release Data Operator, and Release Owner attestations are bound to the evidence artifact.
