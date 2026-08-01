# Decide a run-scoped publication boundary for Daily Identity Refresh

Type: grilling
Status: resolved
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

## Answer (2026-08-01)

Adopt a **run-scoped reducer** for Daily Identity Refresh. It replaces the
current per-500-CIK canonical publication with these explicit stages:

1. A dedicated pre-map task fetches global ticker/reference data once and
   persists an immutable, run-bound reference snapshot.
2. Each serialized CIK batch writes an immutable Identity Refresh Batch Delta
   and declares its status in the run manifest. It does not hydrate, merge, or
   publish canonical silver.
3. A sole Identity Refresh Reducer verifies the selected universe, image,
   reference snapshot, and every declared batch outcome. Only a complete,
   successful manifest may proceed.
4. The reducer processes deltas in manifest order, merges them and the one
   reference snapshot with canonical silver, and uses the existing immutable
   staging plus ETag-guarded promotion. Ambiguous same-key conflicts remain
   terminal and fail closed.

### Concurrency and recovery

`MaxConcurrency=1` remains the identity-refresh execution boundary for this
initial implementation. Successful batch deltas survive a failed sibling;
only a failed batch may be retried, and only under the identical run id,
selected CIK universe, reference snapshot, and immutable warehouse image.
The reducer never runs against a partial manifest.

An interrupted reducer or `PromotionConflictError` retries **only the
reducer**, rehydrating canonical and re-merging the unchanged verified inputs.
The implementation must use a bounded retry policy and surface terminal
exhaustion to the operator; it must not silently repeat batches or substitute
new inputs.

### Observability, migration, and acceptance

The run manifest and events must expose the selected CIK universe/count,
batch ids and outcomes, immutable delta checksums/locations, reference-snapshot
identity, reducer attempts, canonical baseline and resulting ETags, merge
order, and the exact number of canonical promotions. Existing generic
`bootstrap-fundamentals --mode company-identity` behavior remains unchanged
for non-daily callers; the migration is a new daily-specific orchestration and
reducer path, followed by removal of the daily path's per-batch publication.

The recurring schedule remains disabled. Activation requires a new
immutable-image, full-chain production execution proving all declared batches
completed, exactly one canonical publication occurred, existing canonical
integrity protections held, and the total daily execution completed within
six hours.

Follow-up: [Implement run-scoped Daily Identity Refresh publication](61-implement-run-scoped-daily-identity-publication.md).
