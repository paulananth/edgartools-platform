# Capture the Production S3 Request-Attribution Baseline

Type: task
Status: open
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
