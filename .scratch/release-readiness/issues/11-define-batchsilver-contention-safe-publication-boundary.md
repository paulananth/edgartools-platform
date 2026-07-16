# Define the BatchSilver Contention-Safe Publication Boundary

Type: grilling
Status: resolved
Blocked by: 03
Blocks: 06

## Question

Which publication architecture must ensure that MaxConcurrency=4 BatchSilver tasks never perform an unguarded last-writer-wins upload to the same monolith or shard object—distinct immutable batch outputs with deterministic consolidation, shard-level serialization, or conditional versioned rehydrate-and-merge—and what compatibility and recovery contract must downstream full-dataset readers observe?

## Resolution

Selected conditional versioned rehydrate-and-merge. Each publisher semantically merges its partial local DuckDB with canonical, writes a unique staging object, and performs one atomic S3 conditional write using `If-Match` or `If-None-Match`. Conflict responses fail the task for bounded full-command retry, which must rehydrate and re-merge. Downstream readers retain the canonical monolith path and may run only after the zero-tolerance BatchSilver Map succeeds.

The implementation now attaches the precondition to the S3 write itself; the prior read-check followed by an ordinary write was not atomic. Unit tests cover replacement, first creation and conflict rejection, while existing semantic-merge tests cover preservation and fail-closed behavior.

Decision and recovery contract: [`docs/release-readiness/batchsilver-contention-safe-publication-boundary.md`](../../../docs/release-readiness/batchsilver-contention-safe-publication-boundary.md)
