# Design the MaxConcurrency=4 Data Integrity Proof

Type: prototype
Status: resolved
Blocked by:

## Question

What concrete, bounded validation artifact should prove bronze-to-silver completeness, unique filing identity, shard-manifest coverage, rerun idempotency, zero unintended SEC refetch, and absence of write-contention corruption for a release-candidate BatchSilver run at MaxConcurrency=4?

## Answer

Use one deterministic `maxconcurrency4-data-integrity.json` in the Candidate
Evidence Set, bound to the Release Candidate, warehouse image, execution
definition, BatchSilver manifest, and Release Data Watermark. It fails closed
unless all Map children succeed at exactly MaxConcurrency=4, every touched table
passes its own bronze-to-silver key reconciliation and semantic digest contract,
shard coverage is exact, publication is contention-safe, exact-window refetch
and corruption indicators are zero, and a deterministic 16-batch four-wave
rerun leaves primary-key sets and semantic content unchanged.

Evidence must come from immutable execution-bound input, post-full-run, and
post-rerun snapshots within the Live-Evidence Window. Successful Map items and
clean logs cannot replace direct reconciliation or Publish Contention Safety,
and no hard check may be skipped.

The July 5 execution may be assessed separately as a Historical Reconstructed
Integrity Result if its exact versions remain available, but it cannot satisfy a
current candidate gate. The current unguarded whole-object publication behavior
exposes a separate decision about contention-safe publication.

Full contract:
[MaxConcurrency=4 Data Integrity Proof](../../../docs/release-readiness/maxconcurrency4-data-integrity-proof.md)

Prototype source: branch `prototype/maxconcurrency4-data-integrity-proof`, commit
`284e47e`, path
`.scratch/release-readiness/prototypes/maxconcurrency4-proof/`.
