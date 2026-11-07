# Verified per-load quality evidence

## Destination

Bookkeeping retains immutable silver quality outcomes per work unit. The worker
verifier recomputes them, the run aggregator accepts only admitted receipts,
and the existing OpenMetadata publisher stores and reads back each load result.
OpenMetadata remains the visibility layer; Bookkeeping owns pipeline execution
and evidence admission.

## Decisions so far

- OpenMetadata's native test-result history endpoint supports timestamped results
  and retains a stable load reference in the result summary.
- The shipped UI history association still needs an operator observation; no
  OpenMetadata product customization is in scope.
- Version-2 receipt creation stays disabled until the recovery prerequisites in
  ticket 01 are met.
- The Bookkeeping and OpenMetadata skills are owned by open draft PRs #1432 and
  #1418. Their edits wait for those branches to merge; data-operations guidance
  is updated on this branch.

## Issues

- [01: Implement verified per-load quality evidence](issues/01-verified-per-load-quality-evidence.md)
