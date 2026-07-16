# Implement Strict Relationship Artifact Bulk Load

Type: task
Status: resolved
Blocked by: 16
Blocks: 20

## Task

Implement manifest-driven artifact capture for required proxy, Item 5.02/ambiguous 8-K, and 13F candidates, with fail-closed release workflow behavior and explicit repair manifests.

## Done when

- Required Branch B candidates reach the artifact pipeline without fetching unrelated 8-Ks.
- Missing primary/information-table/raw artifacts become accession failures.
- Branch B release-mode failures cannot be caught and routed onward.
- Cache-hit reruns make zero SEC requests; `--force` requires a bounded repair manifest.
- Circuit-breaker leftovers remain unresolved and fail the run.

## Resolution

Implemented by commit `ddc24d3`: `bootstrap-batch --release-mode` accepts a
generation-bound candidate manifest, sends only required accessions to the artifact
pipeline, fails on missing candidates/artifacts, and requires a bounded repair
manifest for `--force`. Production execution and ledger reconciliation remain ticket 20.
