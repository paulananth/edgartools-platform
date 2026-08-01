# Decide a run-scoped publication boundary for Daily Identity Refresh

Type: grilling
Status: open
Blocked by: 57

## Question

What publication architecture lets the bounded Daily Identity Refresh complete
the company-identity batches within its at-most-six-hour full-chain evidence
bound without weakening the canonical silver integrity and recovery guarantees?

## Context

[Root-cause the excessive bounded Daily Identity Refresh runtime](57-root-cause-bounded-daily-identity-runtime.md)
measured that each 500-CIK batch spends roughly 33 minutes merging and
uploading the whole 1.07 GB canonical DuckDB artifact. `MaxConcurrency=1` is
intentional because concurrent canonical writers can lose a publication.

## Decision criteria

- Retain strict fail-closed company-identity semantics and immutable evidence.
- Preserve the ETag/merge protection against lost canonical writes.
- Publish the canonical database no more often than demonstrably necessary;
  assess one publication per refresh run as the baseline.
- Refresh global ticker/reference data once per refresh, not once per CIK
  batch.
- Define bounded recovery/idempotency behavior for failed or interrupted
  batches and their aggregate publication.
- Require a new immutable-image full-chain timing execution before recurring
  schedule activation.

## Done when

An approved design identifies the exact aggregation/publication seam,
concurrency and recovery contract, observability, migration scope, and
acceptance evidence for a subsequent implementation ticket. No implementation
is authorized by this decision ticket.
