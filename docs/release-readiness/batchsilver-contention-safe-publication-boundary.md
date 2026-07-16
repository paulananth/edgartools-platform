# BatchSilver Contention-Safe Publication Boundary

## Decision

Use **conditional versioned rehydrate-and-merge** for the canonical silver DuckDB. BatchSilver remains parallel at `MaxConcurrency=4`, while downstream readers retain the stable full-dataset object:

```text
s3://<warehouse-bucket>/warehouse/silver/sec/silver.duckdb
```

Distinct immutable batch databases plus a new consolidator would require changing every full-dataset reader, and shard-level serialization would reduce useful parallelism while the monolith fallback remains supported. Conditional publication provides the smallest compatible boundary: semantic merge prevents partial candidates from deleting canonical rows, and an atomic S3 write precondition prevents stale merged results from replacing a newer canonical object.

Amazon S3 evaluates `If-Match` and `If-None-Match` as part of the write operation. A mismatched concurrent write fails with `412 Precondition Failed`; concurrent operations can also return `409 Conflict`. [Amazon S3 conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html)

## Publication protocol

Every remote silver publisher must execute this protocol:

1. Read the canonical object's existence, ETag and version ID as the publication baseline.
2. Hydrate canonical bytes and construct a fresh local merged candidate using the protected-table registry.
3. Fail closed on an unclassified domain table, destructive schema change, ambiguous same-key conflict, corrupt database or missing candidate.
4. Write the merged bytes to a unique `_staging/<token>/...` S3 key. The staging key is immutable for that attempt and never aliases the canonical key.
5. Promote with one atomic S3 conditional write:
   - use `If-Match: <baseline-etag>` when canonical existed;
   - use `If-None-Match: *` for first publication.
6. Record the baseline ETag, staged checksum, returned canonical ETag/version ID, merged-table set, execution ID and batch identity.

A pre-write HEAD followed by an ordinary PUT is explicitly forbidden because another writer can land between those operations. The conditional header must be attached to the canonical PUT or conditional multipart completion itself.

## Semantic merge contract

The canonical object is monotonic under ordinary BatchSilver publication:

- canonical-only business keys are retained;
- candidate-only business keys are inserted;
- identical same-key rows are unchanged;
- a candidate replaces a same-key row only when the table's declared non-null authority value is strictly newer;
- tied, missing-authority or otherwise ambiguous differences fail the entire publication;
- additive schema evolution is allowed only for classified tables;
- dropped/retyped canonical columns and unclassified domain tables fail closed;
- operational checkpoint tables are explicitly excluded from semantic merge and cannot establish data completeness.

The reviewed policy registry in [`silver_protection.py`](../../edgar_warehouse/silver_protection.py) is part of the release candidate. Adding a silver domain table without adding and testing its business key and conflict policy blocks publication.

## Conflict and retry contract

S3 `404`, `409`, or `412` responses from conditional promotion are `PromotionConflictError`, a transient publication conflict. The staged candidate remains available for diagnostics. The current ECS task fails, and the Step Functions BatchSilver item retry reruns the complete command with exponential backoff.

Every retry must rehydrate the latest canonical object and repeat semantic merge; it must never promote the stale staged payload directly. BatchSilver has a bounded retry budget. Exhaustion fails the Map because tolerated failure is zero, so MDM, export, graph and gold stages do not consume a partial silver state.

Authentication/authorization failures, unsupported conditional-write capability, schema conflicts, corrupt data and semantic conflicts are not contention retries. They require operator action.

## Downstream compatibility boundary

Full-dataset readers continue reading the canonical `silver/sec/silver.duckdb` object and require no path or schema-discovery change. They may start only after BatchSilver completes successfully. A reader must bind its evidence to the canonical ETag/version returned by the final successful publication and must not combine a pre-Map object version with post-Map data.

The unique staging namespace is not a reader interface. Staged objects are retained for a bounded diagnostic period and may be garbage-collected only after the execution and its evidence are terminal.

The existing shard-manifest path remains supported where a complete manifest is present. Monolith fallback is allowed only through this same guarded publication protocol; fallback is no longer permission to perform an ordinary overwrite.

## Recovery and repair

- **Conditional conflict:** allow the bounded task retry to rehydrate, re-merge and conditionally publish.
- **Retry exhaustion:** stop the full chain, inspect staged/canonical evidence, and rerun only after the contention or capacity cause is understood.
- **Semantic conflict:** quarantine the conflicting business keys and require a policy/data repair; generic retry cannot select a winner.
- **Bad successful publication:** restore a reviewed prior S3 version, then rerun the complete candidate from the unchanged bronze watermark. Do not copy a staging object directly over canonical.
- **Destructive schema repair:** use the separately audited repair path with operator, reason, dry-run diff and a new release candidate; ordinary BatchSilver cannot force it.

## Release proof

Ticket 11 is implemented only when all of the following are true for the release candidate:

- tests prove `If-Match` replacement, `If-None-Match` first creation and atomic conflict rejection;
- semantic merge tests prove canonical-row preservation, deterministic authority, ambiguous-conflict failure, and fail-closed schema/table classification;
- the deployed BatchSilver definition uses `MaxConcurrency=4`, zero tolerated failures and bounded task retry;
- a live execution records at least two overlapping publishers or a deliberately injected stale publisher, with exactly one stale conditional promotion rejected and successfully re-merged on retry;
- final table reconciliation, publication-version lineage and the bounded idempotency rerun required by the MaxConcurrency=4 Data Integrity Gate pass.

Unit and architecture tests establish implementation readiness. The live execution remains release evidence, not a reason to leave this architecture ticket open.

## Ownership

- Warehouse Builder: semantic registry, conditional publisher and tests.
- AWS Operator: deployed definition, task retry, S3 versioning and live conflict evidence.
- Warehouse Operator: table policies, reconciliation and recovery approval.
- Release Owner: binds the final publication version and Data Integrity Gate evidence to the Release Candidate.
