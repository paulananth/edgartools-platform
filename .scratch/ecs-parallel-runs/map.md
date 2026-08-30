# Parallelize the MDM Residual Security Pipeline Safely

Labels: `wayfinder:map`

GitHub mirror: [Parallelize the MDM Residual Security Pipeline Safely](https://github.com/paulananth/edgartools-platform/issues/510)

## Destination

A production-safe residual-security MDM Pipeline Machine whose independent
entity and relationship stages execute in two bounded parallel waves. The
source-controlled implementation and rollout are permitted only after a
disposable canary proves parity, useful speedup, cost safety, and failure
recovery.

## Notes

- The authoritative feature contract is [Specify Safe Parallel Execution for
  the MDM Residual Security Pipeline](https://github.com/paulananth/edgartools-platform/issues/509).
- This map explicitly carries execution through two ordered tickets: first a
  controlled test-run phase, then implementation and rollout.
- The primary test seam is a complete disposable Standard Step Functions
  execution. Generated-ASL tests support that seam but cannot replace it.
- Do not start the test-run phase until the residual-security machine-profile
  sizing cohort is terminal and its accepted immutable profile is frozen.
- The canary changes topology only. It reuses the accepted image, task
  revisions, commands, limits, input, and database population.
- Before implementation edits, run the repository-required GoF refactor review
  and inspect relevant generator history. Do not force a new pattern.
- Preserve the MDM Tail Sequencing Skeleton, Per-Type Exact Relationship
  Parity, generation-scoped verification, individual task Retry/Catch
  behavior, and the workflow's absence of Gold Refresh.
- Branch cancellation is best-effort even with ECS stop permission. Partial
  work detection and safe rerun evidence are mandatory gates.
- This checked-in map is the canonical tracker. The linked GitHub issues mirror
  the map for external coordination; keep both representations aligned when a
  ticket is claimed or resolved.

## Decisions so far

None. Resolution detail will be recorded on the linked tickets and indexed
here after each ticket closes.

## Frontier

- [Prove the Two-Wave Parallel Residual Pipeline with a Controlled Canary](issues/01-prove-two-wave-parallel-residual-pipeline.md)
  is the only unblocked ticket.
- [Implement and Roll Out the Proven Two-Wave Parallel Residual Pipeline](issues/02-implement-two-wave-parallel-residual-pipeline.md)
  is blocked by the controlled-canary ticket.

## Not yet specified

None. The requested route is deliberately two-stage and fully specified:
prove the topology, then implement only if it passes.

## Out of scope

- Entity-resolution concurrency already implemented inside `mdm run`.
- Machine-profile resizing or combining sizing and topology evidence.
- SQL, algorithm, S3, network, or cross-region database optimization inside
  individual stages.
- Parallelizing `MdmExport`, `MdmSync`, or `MdmVerify`.
- Relationship semantics, target limits, schema, graph scope, IAM broadening,
  or unrelated workflow changes.
