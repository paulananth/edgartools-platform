# Observe loads in OpenMetadata

Bookkeeping owns load state. A separate platform tool copies read-only
observations to existing OpenMetadata catalog pipelines and verifies readback.
Reporting cannot start, stop, retry or complete a load.

Use the private Bookkeeping runtime environment and privately set
`OPENMETADATA_URL` and `OPENMETADATA_TOKEN` with pipeline-status write permission.
The catalog pipelines must already exist through Rules catalog publication.

```bash
# Check every retained load and its catalog identity without writing.
edgar-warehouse observe loads --all --dry-run

# Publish one observation for every retained load, then verify it.
edgar-warehouse observe loads --all

# Repeat discovery for one hour, at least 60 seconds apart.
edgar-warehouse observe loads --all --interval 60 --duration 3600

# Inspect authoritative detail or retry reporting for one run.
edgar-warehouse bookkeeping observation <run-id>
edgar-warehouse observe loads --run <run-id>
```

Run one reporter owner for an instance. A local lock prevents duplicate reporter
processes on one host; it does not coordinate different hosts. The repeat option
is bounded, not an installed service. Arrange its lifecycle through the normal
platform runner when continuous reporting is required. New loads arriving after
a sweep starts are discovered on the next sweep. The interval is measured after
a sweep; reporting age includes sweep time and any outage.

The JSON result gives discovered, confirmed, pending and failed counts. A dry run
is pending. A confirmed load has matching native readback. Failed run references
and safe cause codes support a targeted retry; any failed report or incomplete
discovery gives a nonzero exit status. A successful HTTP response alone is
insufficient. Run discovery uses stable pages, including loads sharing a creation
time. `bookkeeping runs --before <last-run-id>` exposes the same cursor.

## Read a load

The native execution ID is the Bookkeeping run ID. Its timestamp is a stable
history key within 999 milliseconds of creation time; retries find and reuse
that execution ID's key. Loads sharing a creation timestamp receive distinct
free keys. A full key window is refused, preserving existing records. Actual
creation time remains separately recorded in parameters; the key is not a clock.
Use `parameters.bookkeeping.observedAt` to determine observation freshness.
If reporting stops, the last status is stale; it is not evidence the load failed.

| Bookkeeping state | Native display | Exact detail |
|---|---|---|
| running | Pending | `parameters.bookkeeping.state` remains running |
| waiting | Pending | Remains waiting |
| blocked | Failed | Remains blocked; inspect Bookkeeping for recovery |
| complete | Successful | Requires consistent verified-unit, check and delivery evidence |

Parameters retain all step-state work-unit counts, attempt/error counts, expected
units, final boolean checks and pending Journal deliveries. Counters are decimal
strings so JSON readers preserve values beyond floating-point precision. They
are work units, not row counts. Output row counts and data-quality results are
explicitly `not_reported`; no fabricated results or raw error messages are sent.
Compacted evidence, unknown pipelines, stale updates and timestamp conflicts
remain explicit reporting failures. A missing record remains unobserved.

## Native API contract

The catalog endpoint is `PUT /api/v1/pipelines/{fqn}/status`, followed by GET with
`startTs` and `endTs` covering that timestamp. Use `executionId`,
`executionStatus`, `taskStatus` and `parameters` from the pinned
[catalog pipeline schema](https://github.com/open-metadata/OpenMetadata/blob/2.0.2-release/openmetadata-spec/src/main/resources/json/schema/entity/data/pipeline.json).
The server Swagger document can conflate catalog and ingestion definitions named
`PipelineStatus`; ingestion's `runId`/`pipelineState` fields are a different API.
Native readback adds defaults; supplied values must still match exactly.

The generic Bookkeeping observation is one SQL statement over run state, complete
step aggregates and delivery backlog. No OpenMetadata dependency, schema change
or callback is added to the control engine. Credentials, raw receipts, record
keys, artifact locations and raw logs stay out of the report.
