# Replace the Dominant S3 Request-Churn Paths

Type: task
Status: open
Blocked by: 02

## Question

Which evidence-ranked warehouse call sites can be changed from broad listing or
repeated existence probes to immutable run-manifest lookup, exact-key access,
or bounded prefix/batch reads so that the measured avoidable Tier-1 request
volume is removed without changing results?

Implement only contributors demonstrated by [Capture the Production S3
Request-Attribution Baseline](02-capture-production-s3-request-attribution-baseline.md).
Preserve conditional immutable Bronze writes, checksum/conflict behavior,
Silver-Once idempotency, exact run membership, retry/resume semantics, and
Snowflake publication completeness. Add request-count regression tests at the
storage-adapter and affected-workflow boundaries.
