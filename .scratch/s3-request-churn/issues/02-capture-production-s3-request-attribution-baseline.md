# Capture the Production S3 Request-Attribution Baseline

Type: task
Status: superseded by the rebuild (2026-10-13 17:31 ET): the pipeline it changes (the retired pipeline's S3 traffic) was retired (platform validation 2a/2b, #764 and #766; the DuckDB silver store, silver-merge-engine-migration 17); the configured platform (Rules, Bookkeeping, Change Journal, Clean MDM) replaces it. Reopen as a new ticket if the need still applies
Blocked by: 01

## Question

Using the bounded method selected by [Confirm a Bounded S3 Request-Attribution
Method](01-confirm-bounded-s3-request-attribution-method.md), what production
bucket/prefix/operation/workflow call distribution accounts for at least 95%
of Tier-1 requests during one representative immutable-image execution?

Capture a versioned, secret-safe evidence artifact that binds the measurement
window, image digest, Step Functions execution, CloudWatch metric configuration,
application counters, Cost Explorer totals, and the ranked request contributors.
Do not change retention, object contents, or workload semantics while measuring.
