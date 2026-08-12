# Bounded S3 request-attribution method

Research date: 2026-08-01  
Scope: production account `690839588395`, `us-east-1`  
Decision purpose: establish a prospective measurement standard before changing
S3 access behavior or retention.

## Decision

Use **four temporary, unfiltered S3 CloudWatch request-metric
configurations**, one on each production bucket, plus **fixed-cardinality
application request counters emitted once per task/run**. Do not use
prefix-filtered S3 request metrics for the baseline: AWS explicitly says that
`ListObjects` requests do not produce metrics for filtered configurations, and
LIST is both a Tier-1 operation and the suspected source of churn.

The four configurations are:

| Bucket role | Production bucket | Metrics configuration | Application prefix class |
| --- | --- | --- | --- |
| Bronze | `edgartools-prod-bronze-690839588395` | `s3-request-baseline-entire-bucket-20260801` (no filter) | `warehouse/bronze/` |
| Warehouse | `edgartools-prod-warehouse-690839588395` | same ID, bucket-local (no filter) | `warehouse/` |
| Snowflake export | `edgartools-prod-snowflake-export-690839588395` | same ID, bucket-local (no filter) | `warehouse/artifacts/snowflake_exports/` |
| Terraform state | `edgartools-prod-tfstate-690839588395` | same ID, bucket-local (no filter) | the four exact state keys listed below, otherwise `other` |

The production Terraform-state keys currently documented by the repository are:

- `accounts/prod/terraform.tfstate`
- `access/aws/prod/terraform.tfstate`
- `snowflake/prod/terraform.tfstate`
- `access/snowflake/prod/terraform.tfstate`

This is the smallest reliable configuration set. One whole-bucket filter is
needed per bucket to retain `ListRequests`; adding prefix filters would create
overlapping metrics and cost but would still not attribute LIST calls. Prefix
is therefore an application dimension, not an S3 metric filter.

## What `Requests-Tier1` means

AWS defines ``region`-Requests-Tier1` as the hourly count of `PUT`, `COPY`, or
`POST` requests for S3 Standard, RRS, and tags, plus `LIST` requests for all
buckets and objects. Tier 2 contains `GET` and other non-Tier-1 requests.
DELETE and CANCEL requests are free. For this workload, the CloudWatch
comparison count is therefore:

```text
cloudwatch_tier1 = Sum(PutRequests) + Sum(PostRequests) + Sum(ListRequests)
```

`PutRequests` includes the destination side of each `CopyObject`; the
non-billable source-side GET also increments `GetRequests`, which must not be
added to the Tier-1 comparison. `AllRequests` is not a billing denominator
because it mixes Tier-1 and Tier-2 traffic. Application instrumentation must
classify the SDK operation explicitly, including multipart upload operations,
tag writes, and copies, rather than infer billing class from a high-level
adapter method name.

Authoritative sources:

- [Understanding AWS billing and usage reports for Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/aws-usage-report-understand.html)
- [Amazon S3 request metrics and dimensions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/metrics-dimensions.html)
- [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/)

## Why prefix-filtered request metrics are rejected

AWS allows at most 1,000 request-metric configurations per bucket and supports
prefix, object-tag, access-point, or conjunction filters. Each configuration
enables the full request-metric set. However, a filtered configuration matches
only requests operating on one object; AWS specifically states that
`DeleteObjects` and `ListObjects` return no metrics for filtered
configurations. An unfiltered configuration does report object operations and
bucket-content listing operations.

Consequences:

1. A prefix-filter-only design would systematically hide the request type this
   investigation is intended to find.
2. Four unfiltered configurations provide bucket and operation attribution.
3. Fixed application prefix classes provide the missing prefix, workflow, and
   run attribution without multiplying CloudWatch metric series.
4. The whole-bucket measurement also exposes Terraform/operator or
   AWS-managed traffic that has no application counter; it appears as the
   unattributed remainder instead of disappearing.

Authoritative sources:

- [Creating a metrics configuration filtered by prefix, tag, or access point](https://docs.aws.amazon.com/AmazonS3/latest/userguide/metrics-configurations-filter.html)
- [CloudWatch metrics configurations for Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/metrics-configurations.html)
- [Creating a request-metric configuration for all bucket objects](https://docs.aws.amazon.com/AmazonS3/latest/userguide/configure-request-metrics-bucket.html)

## Application counter contract

Instrument every S3 wire attempt made by the warehouse runtime, including SDK
retries and each paginator page. Aggregate in memory and emit one structured
summary event per ECS task, plus one workflow summary after all tasks finish.
Use the existing task log/run evidence path; do **not** publish one CloudWatch
custom metric per run, object, CIK, accession, or key.

Required binding fields, once per summary:

| Field | Rule |
| --- | --- |
| `schema_version` | Fixed event schema version. |
| `aws_account_id`, `aws_region` | Must equal `690839588395`, `us-east-1` for the accepted baseline. |
| `image_digest` | Full immutable ECR `sha256:` digest, not only a mutable tag. |
| `git_sha` | Source commit embedded in or associated with the immutable image. |
| `task_definition_arn` | Full ECS family/revision ARN. |
| `step_functions_execution_arn` | Immutable execution identity. |
| `workflow`, `run_id` | Bounded workflow name and operator-supplied execution/run ID. |
| `task_started_at`, `task_ended_at` | UTC timestamps defining the request window. |

Required sparse counter dimensions:

| Dimension | Bounded values |
| --- | --- |
| `bucket_role` | `bronze`, `warehouse`, `snowflake_export`, `terraform_state`, `other` |
| `prefix_class` | The three runtime roots above; four exact Terraform-state keys; `other` |
| `api_operation` | Actual S3 API name such as `ListObjectsV2`, `HeadObject`, `GetObject`, `PutObject`, `CopyObject`, multipart operations, or `Other` |
| `billing_class` | `tier1`, `tier2`, `free`, `unknown` |
| `outcome` | `2xx`, `3xx`, `4xx`, `5xx`, `transport_error` |
| value | Count of HTTP attempts, not number of keys returned or objects affected |

Do not record the full object key, CIK, accession, request ID, task ARN, image
digest, or run ID as a CloudWatch metric dimension. The identity fields belong
in the one structured event. Prefix classification uses longest-known-prefix
matching and maps every unmatched key to `other`, so the cardinality cannot
grow with the data.

The counter must sit below broad-list/existence-check abstractions so it counts
paginator pages and SDK retries. If instrumentation cannot observe a retry as a
wire attempt, it must add the SDK-reported retry count to the logical call and
mark that counter `retry_count_inferred=true`.

## Observation and reconciliation protocol

1. Re-verify caller identity and region immediately before any live action.
2. Record all pre-existing bucket metric configurations. Refuse to overwrite a
   configuration with the chosen ID.
3. Add the four no-filter configurations. Do not enable access logging,
   CloudTrail data events, Storage Lens advanced metrics, or object tags for
   this measurement.
4. Wait **at least 15 minutes after CloudWatch begins tracking request
   metrics** before starting the bounded run. AWS documents about 15 minutes
   to begin tracking; the implementation ticket should confirm non-empty
   datapoints before launch rather than relying only on wall-clock sleep.
5. Capture a 15-minute pre-run idle baseline, run exactly one named production
   execution on one immutable image, and retain metrics for a two-hour
   post-run drain. The two-hour drain is an operational allowance, not an AWS
   completeness guarantee: AWS documents request metrics as delayed and
   best-effort.
6. Retrieve 1-minute `PutRequests`, `PostRequests`, and `ListRequests` sums for
   each bucket/configuration from 15 minutes before the earliest task start to
   two hours after the latest task end. Retain `AllRequests`, `HeadRequests`,
   `GetRequests`, `4xxErrors`, and `5xxErrors` only as diagnostics.
7. Sum application Tier-1 attempt counters over the same run. Report the
   matrix by bucket role, fixed prefix class, API operation, workflow, and run.
8. For each bucket and in aggregate, calculate:

   ```text
   observed_tier1 = CW PutRequests + PostRequests + ListRequests
   attributed_tier1 = application tier1 wire attempts
   attribution_ratio = attributed_tier1 / observed_tier1
   unexplained = observed_tier1 - attributed_tier1
   ```

   CloudWatch is best-effort, so negative `unexplained` is possible. Accept the
   baseline only when aggregate and every material bucket (at least 5% of the
   aggregate) reconcile within ±5%, all application counters carry immutable
   image and execution identities, and at least 95% of the observed Tier-1
   count is assigned to a non-`other` bucket/prefix/operation/workflow/run
   cell. If application counts exceed CloudWatch by more than 5%, do not
   relabel the excess as attributed; repeat the observation or add a more
   authoritative temporary trace in a new ticket.
9. After AWS billing refreshes, compare the enclosing UTC day/hour (where an
   hourly usage report is available) with ``USE1-Requests-Tier1`` as a sanity
   check. This is not the 95% gate because Cost Explorer reflects usage only
   through the previous day, may update later than 24 hours, and cannot isolate
   this run from unrelated requests at the required bucket/prefix granularity.
   Wait for two daily refreshes (up to 48 hours) before recording the billing
   comparison.
10. Export the metric datapoints and counter summaries into the ticket evidence,
    then delete exactly the four temporary configurations and independently
    list configurations on every bucket to prove the IDs are gone.

AWS says request metrics are one-minute metrics, begin tracking after about 15
minutes, and are delivered best-effort: completeness and timeliness are not
guaranteed. Cost Explorer refreshes at least daily, with some current-period
data arriving later than 24 hours.

Authoritative sources:

- [Best-effort S3 CloudWatch request-metric delivery](https://docs.aws.amazon.com/AmazonS3/latest/userguide/metrics-configurations.html)
- [Cost Explorer data freshness](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-exploring-data.html)
- [Retrieving CloudWatch metric data](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/metrics-classic-getdata.html)

## Cost bound

Each configuration can publish the 16 request metrics documented in the
`AWS/S3` namespace. Four configurations therefore create at most 64 metric
series when every metric is active. At the current US East first-tier price of
$0.30 per metric-month, the full-month ceiling is $19.20 before any applicable
free tier. CloudWatch custom metrics are prorated hourly and charged only in
hours when data is sent. Keeping all 64 active for 72 hours has a conservative
ceiling of approximately **$1.92** using a 720-hour pricing month; the actual
charge can be lower because operation-specific series appear only when those
operations occur and the account might have remaining free-tier metrics.

A single `GetMetricData` retrieval can request up to 500 metrics. Requesting
64 metrics once costs less than $0.001 at $0.01 per 1,000 metrics requested.
The application side adds only bounded structured summaries to the existing
ECS log stream; it creates no custom metric series. Keep each task summary
under 10 KiB and emit it once, so log volume remains proportional to task
count rather than S3 request count.

Authoritative sources:

- [Amazon CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/)
- [CloudWatch custom-metric hourly proration](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_billing.html)
- [S3 request metrics are billed at CloudWatch rates](https://docs.aws.amazon.com/AmazonS3/latest/userguide/configure-request-metrics-bucket.html)

## Teardown

For each of the four buckets, delete only
`s3-request-baseline-entire-bucket-20260801`, then call
`ListBucketMetricsConfigurations` and preserve the response proving that ID is
absent while all pre-existing configurations remain unchanged. AWS states that
charges for a request-metric filter stop when it is deleted. The measurement
must not create or alter lifecycle rules, server access logging, object tags,
versions, retention, encryption, or Bronze objects.

Authoritative source:

- [Deleting an S3 request-metrics filter](https://docs.aws.amazon.com/AmazonS3/latest/userguide/delete-request-metrics-filter.html)

## Historical limit

Exact retrospective attribution of the July 29–31 spike is impossible from the
currently available evidence. The buckets had neither request-metric
configurations nor server access logging during the spike. CloudWatch cannot
backfill metrics that were never enabled, and server access logging is
best-effort and begins only after configuration changes take effect. Billing
reports can retain hourly ``Requests-Tier1`` usage and an operation field, but
AWS documents that `lineItem/ResourceId` is blank for API-request usage types;
therefore those records cannot reconstruct the missing bucket, object prefix,
workflow, run, or immutable-image dimensions.

The known daily totals remain valid as a cost/volume symptom, not an
attribution baseline. The first defensible attribution is prospective.

Authoritative sources:

- [S3 server access logging delivery and activation limitations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ServerLogs.html)
- [AWS Cost and Usage Report line-item fields](https://docs.aws.amazon.com/cur/latest/userguide/Lineitem-columns.html)

## Acceptance handed to the baseline ticket

The production baseline is acceptable only if its evidence contains:

- the four before/after metrics-configuration inventories;
- immutable image digest, git SHA, task-definition revisions, execution ARN,
  workflow, and run ID;
- exported one-minute CloudWatch datapoints and bounded counter summaries;
- an attribution matrix assigning at least 95% of observed Tier-1 requests;
- explicit `other` and unexplained counts rather than forced attribution;
- the delayed billing sanity check;
- teardown proof; and
- confirmation that no Bronze artifact, version, checksum, conditional-write
  behavior, idempotency marker, retention rule, or lifecycle rule changed.

