# Confirm a Bounded S3 Request-Attribution Method

Type: research
Status: resolved
Blocked by: none

## Question

What exact combination of AWS S3 request metrics and application-level
instrumentation will attribute at least 95% of production Tier-1 requests by
bucket, bounded prefix, operation, workflow, and run without creating
high-cardinality observability cost or mutating the data plane?

The answer must use current authoritative AWS behavior to specify:

- which Tier-1 operations are represented by the billing usage type;
- the smallest prefix-filter set needed across Bronze, warehouse, Snowflake
  export, and Terraform-state buckets;
- metric publication delay, observation duration, and reconciliation method;
- the application counter/event dimensions needed to bind requests to one
  immutable image and execution;
- expected observability cost and a teardown/disable step after measurement;
- what historical attribution remains impossible because request metrics and
  access logging were not enabled during the spike.

## Answer

Use four temporary **whole-bucket** S3 request-metric configurations—one each
for Bronze, warehouse, Snowflake export, and Terraform state—plus one bounded
application counter summary per task/run. Do not use prefix-filtered S3 request
metrics: AWS explicitly excludes `ListObjects` from filtered configurations,
which would hide the suspected Tier-1 driver. CloudWatch supplies bucket and
operation totals; fixed application prefix classes supply prefix, workflow,
run, and immutable-image attribution without high-cardinality custom metrics.

The baseline waits for CloudWatch tracking to begin, observes one bounded run
with pre/post windows, reconciles `PutRequests + PostRequests + ListRequests`
against application wire-attempt counters within ±5%, and requires at least
95% of the observed Tier-1 count to land in a non-`other` attribution cell.
Metrics remain enabled long enough for delayed datapoints, billing is checked
after two daily refreshes as a sanity check, and the four configurations are
then deleted with before/after inventory proof. The conservative 72-hour
CloudWatch ceiling is about $1.92 for at most 64 series at current US East
first-tier pricing, before any free tier.

Exact retrospective bucket/prefix attribution of the July spike is impossible:
request metrics and access logs were not enabled, neither facility backfills,
and billing records for API-request usage do not provide the missing resource
identity.

Full method and official AWS citations:
[Bounded S3 request-attribution method](../research/01-bounded-s3-request-attribution-method.md).
