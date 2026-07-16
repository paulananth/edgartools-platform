# MaxConcurrency=4 Data Integrity Proof

## Decision

A Release Candidate satisfies the MaxConcurrency=4 Data Integrity Gate only
when one deterministic, secret-safe `maxconcurrency4-data-integrity.json`
artifact reports PASS for every hard check below. Map completion and clean logs
are necessary but cannot substitute for direct data reconciliation, idempotency,
or Publish Contention Safety. No hard check may be `skipped`, `unknown`, or
accepted on a prose basis.

The artifact belongs in the Candidate Evidence Set and is bound to the exact
Release Candidate, Release Data Watermark, execution-specific state-machine
definition, warehouse image digest, and BatchSilver input manifest.

## Execution-bound capture

Evidence is captured in this order within the 24-hour Live-Evidence Window:

1. Freeze and fingerprint the bronze inventory and BatchSilver input manifest.
2. Capture the execution-specific state-machine definition proving
   `MaxConcurrency=4` and the expected child count.
3. Run the complete BatchSilver map.
4. Capture an immutable post-run snapshot of every logical silver object used by
   the run, including a fingerprint of its storage object version.
5. Select and execute the Bounded Idempotency Rerun against the unchanged bronze
   inventory and watermark.
6. Capture a second immutable silver snapshot and generate the final artifact by
   comparing the frozen input, full-run output, and rerun output.

Mutable `latest` silver state, mixed executions, and evidence collected after an
object version can no longer be identified are invalid direct evidence.

## Hard checks

### Candidate and execution identity

- Candidate commit and warehouse image digest match the Release Evidence
  Manifest.
- Bronze inventory, batch manifest, full execution, two silver snapshots, and
  rerun cohort share one Release Data Watermark.
- The execution-specific definition uses exactly `MaxConcurrency=4`.
- Expected child count equals successful child count; failed, timed-out, and
  aborted counts are all zero.

### Table-Specific Reconciliation

A versioned table contract covers every silver table touched by BatchSilver. For
each table it declares its primary key, bronze expectation rule, required-parent
relationships, semantic columns, permitted legitimate-zero outcomes, and
operational columns excluded from semantic comparison.

The artifact records, per table:

- expected and actual row/key counts;
- missing and unexpected primary-key counts;
- duplicate primary-key group count, which must be zero;
- required-parent orphan count, which must be zero;
- SHA-256 of the sorted canonical primary-key set;
- SHA-256 of sorted canonical semantic rows;
- explicit loader outcome counts for optional and one-to-many parsers.

Exact bronze-to-silver key equality is required where the contract says a bronze
record must produce a silver record. Optional parser output may be empty only
when the recorded loader outcome explains that result. Aggregate filing counts
cannot hide partial loss in child tables.

Canonical semantic digests normalize types and nulls, sort by declared primary
key, and exclude only explicitly listed operational provenance fields such as a
run identifier or synchronization timestamp. Business timestamps and values are
not excluded merely because they changed.

### Manifest coverage and Publish Contention Safety

- The shard manifest schema and band topology are valid.
- Every in-scope CIK is covered by exactly one band.
- Every referenced silver object exists in the post-run snapshot.
- The evidence fingerprints the actual post-run object versions; a static shard
  manifest checksum alone is insufficient after subsequent writes.
- Every simultaneously active publisher either writes a distinct immutable
  object or uses a conditional/versioned protocol that rejects a stale publish,
  rehydrates the winning version, reapplies its change, and completes without a
  lost update.

Any overlapping unguarded publication to the same monolith or shard object is a
hard FAIL even if tasks succeed, logs are clean, and sampled final counts match.
A `shard_manifest_missing_monolith_fallback` event is therefore not automatically
the failure; unguarded overlapping publication caused by that fallback is.

### Bounded Idempotency Rerun

The rerun contains exactly 16 batches, producing four complete concurrency
waves. Selection occurs before the full run and is deterministic from the frozen
batch manifest. It covers all routing bands and prioritizes highest-volume,
band-boundary, parser-diverse, already-loaded/no-op, and guarded shared-publication
cases. Category overlap is de-duplicated; remaining slots are filled by stable
hash order. The selection list and its SHA-256 digest enter the evidence artifact.

The rerun passes only when:

- the input watermark is unchanged;
- every table's canonical primary-key-set and semantic-row digests are unchanged;
- no new bronze object is created;
- `sec_pull_started` and `filing_artifact_pipeline_started` are both zero in the
  exact rerun window;
- all 16 rerun children succeed with no failed, timed-out, or aborted child.

### Observability

The exact full-run and rerun windows must contain zero known lock, DuckDB,
partial-write, duplicate, corruption, stale-publication, or unresolved
conditional-conflict indicators. Zero indicators support the direct checks; they
do not replace them.

## Artifact contract

`maxconcurrency4-data-integrity.json` contains:

- evidence-schema and collector versions;
- candidate, image, watermark, definition, batch-manifest, and cohort
  fingerprints;
- UTC capture start/end and expiry timestamps;
- full Map and rerun Map statistics;
- one result object for every hard check;
- per-table reconciliation and semantic digests;
- shard topology, logical-object coverage, object-version fingerprints, and
  maximum overlapping publisher evidence;
- exact-window sanitized event counts;
- final `PASS` or `FAIL`, failure codes, and sanitization result.

Raw S3 paths, object version IDs, AWS account identifiers, ARNs, CIK/accession
samples, and raw log messages stay outside Git. The artifact uses stable logical
names, counts, and SHA-256 fingerprints.

## Historical reconstruction

The July 5 execution may receive a **Historical Reconstructed Integrity Result**
only if its exact execution definition, image, bronze inventory, silver object
versions, logs, and table state remain reconstructable. That result is labeled
historical and may support engineering confidence. It cannot satisfy a current
Release Candidate gate or the Live-Evidence Window.

## Current implementation implication

The release-readiness implementation now uses the publication architecture in
[`batchsilver-contention-safe-publication-boundary.md`](batchsilver-contention-safe-publication-boundary.md):
protected-table semantic rehydrate-and-merge, a unique staging object, and an
atomic S3 conditional write on the canonical key. The prior read-check followed
by an ordinary overwrite was not atomic and cannot establish Publish
Contention Safety.

Implementation tests make ticket 11 decision-complete. A current-candidate live
execution must still capture conditional-publication lineage and satisfy every
reconciliation and bounded-rerun check in this document before the Data
Integrity Gate can pass.

## Ownership

- **Candidate Builder** — owns the table-contract schema, collector, evaluator,
  deterministic cohort selector, and automated checks.
- **AWS Operator** — owns execution-bound capture, exact-window event evidence,
  and immutable storage-object references.
- **Warehouse Operator** — reviews reconciliation rules, legitimate-zero parser
  outcomes, and semantic projections.
- **Release Owner** — attests the final artifact for the Data Integrity Gate.

These are logical roles; no named human implementer is assigned yet.

## Prototype source

The validated in-memory logic prototype is preserved on branch
`prototype/maxconcurrency4-data-integrity-proof` at commit `284e47e`, under
`.scratch/release-readiness/prototypes/maxconcurrency4-proof/`.
