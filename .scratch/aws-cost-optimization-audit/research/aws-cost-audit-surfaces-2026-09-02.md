# Safe AWS Cost-Audit Surfaces

Research date: 2026-09-02
Scope: AWS account `690839588395`, with `edgartools-*` resources in
`us-east-1` as the default attributable resource scope.

## Decision

A useful weekly audit can remain read-only and inexpensive. It should use a
small, fixed number of Cost Explorer queries to identify material services and
drift, then inspect resource metadata only for those services. It should not
enable telemetry, create exports, mutate lifecycle policies, resize tasks, or
delete anything.

The audit must preserve this boundary:

- An **Optimization Candidate** is evidence that a cost might be avoidable.
  It may be reported and ranked.
- **Remediation** is any state-changing action. It requires separate operator
  authorization and service-specific safety evidence; the audit may only print
  guidance.

Cost data alone never authorizes remediation. A zero-utilization metric, an old
timestamp, or an apparently unreferenced resource can be a false positive when
the resource is a rollback target, disaster-recovery asset, immutable evidence,
an infrequent scheduled dependency, or used from another Region or account.

## Cheapest Safe Query Plan

1. Call Cost Explorer once for the previous complete month and current
   month-to-date, grouped by service, using `UnblendedCost`. Mark current-month
   results provisional whenever `Estimated` is true.
2. Make one additional Cost Explorer query grouped by `SERVICE` and
   `USAGE_TYPE` (or `OPERATION`) only for material or drifting services. Each
   paginated Cost Explorer API request costs USD 0.01, so queries and pagination
   must be bounded rather than performed once per resource.
3. Inventory only `edgartools-*` resources using `List`, `Describe`, and `Get`
   APIs. If a service cost cannot be attributed to a resource, report the
   account-level cost and the attribution gap.
4. Reuse free, already-published AWS service metrics and existing telemetry.
   Never enable S3 Storage Lens advanced metrics, ECS Container Insights, high
   resolution metrics, CloudWatch Logs Insights queries, CloudTrail data event
   trails, or another paid collector as part of the audit.
5. Report a candidate when projected savings are at least USD 1/month, a
   service grows more than 20 percent month over month, or a safety/configuration
   drift exists. Missing permissions or delayed metrics produce an
   `insufficient_evidence` finding, not a clean bill of health.

[GetCostAndUsage](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_GetCostAndUsage.html)
supports time ranges, metrics, filters, pagination, and dimensions such as
service and availability zone. Cost Explorer data generally takes about 24
hours to prepare; previous or forecast data can take longer, and current-period
upstream data can be revised. Its end date is exclusive. Each paginated request
against the primary billing view costs USD 0.01.
([Cost Explorer considerations](https://docs.aws.amazon.com/cost-management/latest/userguide/bcm-lite-cost-explorer.html),
[date interval semantics](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_DateInterval.html),
[pricing](https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/)).

The script should show both underlying usage cost and net account impact when
available, keeping credits, refunds, discounts, and tax separate. AWS documents
that Cost Explorer and invoice data can differ due to refresh cadence,
grouping, rounding, and treatment of credits/refunds/tax; the invoice remains
authoritative.
([Billing and Cost Explorer differences](https://docs.aws.amazon.com/cost-management/latest/userguide/differences-billing-data-cost-explorer-data.html)).

## Service Surfaces

### Amazon S3

**Cost drivers.** Current object bytes, noncurrent version bytes, incomplete
multipart-upload parts, storage class, minimum-duration charges, request and
retrieval charges, lifecycle transitions, and data transfer. Lifecycle is not
automatically cheaper: transition requests, retrieval, and minimum storage
durations can outweigh storage savings for small or short-lived objects.
([S3 pricing](https://aws.amazon.com/s3/pricing/)).

**Read-only evidence.** Use:

- `s3:ListAllMyBuckets`, `s3:GetBucketLocation`,
  `s3:GetBucketVersioning`, `s3:GetLifecycleConfiguration`, and relevant
  encryption/public-access metadata getters for every in-scope bucket.
- Existing CloudWatch daily S3 `BucketSizeBytes` and `NumberOfObjects` metrics
  through `cloudwatch:GetMetricData`. AWS states that bucket storage metrics
  include current and noncurrent objects, metadata, delete markers, and all
  parts of incomplete multipart uploads; therefore they are good for total
  scale but cannot attribute those components by themselves.
  ([S3 CloudWatch metrics](https://docs.aws.amazon.com/AmazonS3/latest/userguide/metrics-dimensions.html)).
- Existing S3 Storage Lens free metrics or an already-configured free export,
  when present. Free daily metrics include current-version bytes,
  noncurrent-version bytes, delete markers, and incomplete multipart-upload
  bytes/count at bucket aggregation, with 14 days of query availability.
  ([Storage Lens metrics glossary](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage_lens_metrics_glossary.html),
  [Storage Lens tiers](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage_lens_basics_metrics_recommendations.html)).
- `s3:ListBucketVersions` and `s3:ListBucketMultipartUploads`, with
  `s3:ListMultipartUploadParts` only for an explicitly bounded deep scan. These
  APIs provide exact metadata but generate S3 list requests and can paginate
  heavily, so they should be opt-in or capped by bucket/page count.
  ([required S3 API permissions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-with-s3-policy-actions.html)).

The audit may read Storage Lens configuration with
`s3:ListStorageLensConfigurations` and `s3:GetStorageLensConfiguration` and may
consume an existing export with narrowly-scoped `s3:GetObject`. It must not call
`PutStorageLensConfiguration` to create an export. Creating an export is a
configuration mutation and also creates billable S3 objects.
([Storage Lens permissions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage_lens_iam_permissions.html)).

**Candidate evidence.** Report:

- a material amount of noncurrent bytes with no bounded retention rule;
- incomplete multipart uploads older than the agreed completion window;
- a bucket with growing bytes/cost but no lifecycle rule, clearly labelled as
  a lifecycle-review candidate;
- request/retrieval/transition spend that exceeds the expected storage saving;
- lifecycle policy drift, such as the absence of abort-incomplete-upload rules.

AWS bills uploaded multipart parts until completion or abort, and recommends an
`AbortIncompleteMultipartUpload` lifecycle action. Aborting incomplete uploads
has no early-deletion charge.
([multipart upload billing](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html)).

**False positives and remediation gate.** Noncurrent versions can be required
rollback or audit evidence. Old current Bronze objects are immutable source
evidence, not waste. Delete markers are not equivalent to object data. A
lifecycle transition can add request, retrieval, and early-deletion cost.
Remediation requires classification of the data, retention/legal requirements,
recovery proof, exact candidate keys/versions, projected net savings including
requests, and a reviewed lifecycle or deletion plan. The audit must never issue
`PutBucketLifecycleConfiguration`, `AbortMultipartUpload`, `DeleteObject`, or
`DeleteObjects`.

### Amazon ECS and AWS Fargate

**Cost drivers.** ECS orchestration itself has no additional charge. Fargate
bills the CPU, memory, and configured ephemeral storage requested by a task,
from image-pull start until termination, per second with a one-minute minimum.
The first 20 GB of ephemeral storage is included; only configured storage above
that amount is charged.
([ECS pricing](https://aws.amazon.com/ecs/pricing/),
[Fargate pricing](https://aws.amazon.com/fargate/pricing/)).

**Read-only evidence.** Use:

- `ecs:ListClusters`, `ecs:ListServices`, `ecs:DescribeServices`,
  `ecs:ListTasks`, `ecs:DescribeTasks`, `ecs:ListTaskDefinitions`, and
  `ecs:DescribeTaskDefinition` to map tasks to immutable task-definition
  revisions and requested `cpu`, `memory`, and `ephemeralStorage`.
- Existing free ECS service-level CloudWatch `CPUUtilization` and
  `MemoryUtilization` metrics when the workload is an ECS service.
  ([ECS CloudWatch monitoring](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-metrics.html)).
- Existing Container Insights metrics, when already enabled, for
  `CpuUtilized`, `CpuReserved`, `MemoryUtilized`, `MemoryReserved`,
  `EphemeralStorageUtilized`, and `EphemeralStorageReserved`.
  ([Container Insights ECS metrics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-metrics-ECS.html)).
- Step Functions execution identity, task-definition ARN, input envelope,
  validated-output counters, timestamps, retry/recovery outcome, and immutable
  image/orchestration identity from the platform's durable run evidence.

`DescribeTasks` only guarantees stopped tasks remain visible for at least one
hour, so a weekly audit cannot reconstruct historical task duration or outcome
from ECS alone.
([DescribeTasks retention](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DescribeTasks.html)).
The audit must degrade to `insufficient_evidence` when durable task-bound
evidence is absent.

**Candidate evidence.** Low p95 CPU/memory/ephemeral-storage use can nominate a
specific task-definition revision for a canary. It cannot approve a downgrade.
Candidate evidence must be task-bound and joined to cost per successful,
validated output; aggregate family or cluster utilization is only advisory.

**False positives and remediation gate.** Peaks may be hidden by averages,
different inputs can make runs incomparable, garbage collection can make memory
metrics misleading, a task can finish successfully with incomplete output, and
smaller CPU/memory can increase runtime enough to raise total cost. The current
repository ECS evidence rules remain authoritative: repeated current-image
candidate runs and a matched control must pass correctness, completeness,
identity parity, recovery, idempotency, p95 duration no more than 5 percent
slower, and at least 10 percent lower validated-output cost. No concurrent
candidate/control runs may share mutable MDM state. The audit must never
register a task definition, update a service/state machine, start/stop a task,
or change concurrency.

Do not enable Container Insights solely for this audit. AWS explicitly labels
per-task Container Insights as additional-cost telemetry, while existing
service-level CPU and memory metrics for Fargate services are automatic.
([ECS monitoring costs](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cloudwatch-metrics.html)).

### Amazon CloudWatch

**Read-only evidence.** `logs:DescribeLogGroups` returns retention days and
stored bytes; `logs:DescribeLogStreams` can provide recent stream timestamps;
`cloudwatch:ListMetrics`, `cloudwatch:DescribeAlarms`, and bounded
`cloudwatch:GetMetricData` inspect existing metrics. Cost Explorer usage types
and operations distinguish log ingestion, archival, custom metrics, API
requests, and Container Insights.
([DescribeLogGroups](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_DescribeLogGroups.html),
[CloudWatch cost dimensions](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_billing.html)).

**Candidate evidence.** Material stored bytes with no explicit retention,
unexpected ingestion growth, custom metric cardinality, paid high-resolution
metrics, unused alarms/dashboards, or Container Insights spend can be reported.
No recent log event is insufficient on its own: incident, audit, and infrequent
workflow logs may be intentionally retained. A retention change requires
security/operations approval and confirmation that the group is not recreated
with a longer default. The audit must not call `PutRetentionPolicy`, delete log
groups, or run open-ended Logs Insights queries.

CloudWatch charges can arise from log ingestion and archival, custom metrics,
API retrieval, alarms/dashboards, and Container Insights. Existing service
metrics are often free, while high-cardinality custom metrics and enhanced
telemetry are not.
([CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/)).

### Amazon ECR

**Read-only evidence.** Use `ecr:DescribeRepositories`,
`ecr:DescribeImages`, `ecr:GetLifecyclePolicy`, `ecr:GetLifecyclePolicyPreview`,
`ecr:ListImages`, and `ecr:ListTagsForResource`. Metadata includes compressed
image size, pushed time, tags, digest, and last-recorded pull time.
([ECR authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ecr.html)).

**Candidate evidence.** Old untagged images, duplicate role/revision cohorts,
or images outside a bounded retention policy can be reported after excluding
every currently deployed digest and the reviewed rollback/protected-tag set.
Summing image sizes can overstate savings because layers can be shared; old
`lastRecordedPullTime` is not proof of non-use and is refreshed at most once
per 24 hours.
([DescribeImages fields](https://docs.aws.amazon.com/cli/latest/reference/ecr/describe-images.html)).
ECR charges for stored data and cross-Region/Internet transfer, while same-
Region transfer to Fargate is free.
([ECR pricing](https://aws.amazon.com/ecr/pricing/)).

Remediation must remain behind the repository's existing rollback-registry,
exact-digest, protected-tag, cohort, and reconciliation gates. The audit must
not batch-delete images or put a lifecycle policy.

### AWS Secrets Manager

**Read-only evidence.** `secretsmanager:ListSecrets`,
`secretsmanager:DescribeSecret`, and `secretsmanager:ListSecretVersionIds`
expose ownership, last changed/rotated/accessed dates, replication, and version
metadata without retrieving secret values. Do not grant `GetSecretValue` to the
audit role.
([Secrets Manager authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_secretsmanager.html),
[ListSecrets fields](https://docs.aws.amazon.com/cli/latest/reference/secretsmanager/list-secrets.html)).

Secrets are charged per secret-month and API call.
([Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/)).
An old or missing `LastAccessedDate` is only a candidate: it is Region-specific,
date-resolution metadata, can be affected by eventual consistency, and may not
capture cross-account/replica or break-glass intent. Confirm no resource,
deployment script, task definition, rotation process, or recovery procedure
references the secret before any separately authorized deletion. Service-owned
and legacy compatibility containers need explicit ownership review.

### VPC networking and public IPv4

**Read-only evidence.** Across all enabled Regions use
`ec2:DescribeNatGateways`, `ec2:DescribeVpcEndpoints`,
`ec2:DescribeAddresses`, `ec2:DescribeNetworkInterfaces`,
`ec2:DescribeRouteTables`, and `ec2:DescribeInternetGateways`; correlate these
with Cost Explorer usage types. IPAM Public IP Insights can be consumed if it
already exists, but the audit must not create IPAM resources.
([EC2/VPC authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html),
[Public IP Insights](https://docs.aws.amazon.com/vpc/latest/ipam/view-public-ip-insights.html)).

NAT gateways charge per provisioned hour and processed GB. Public IPv4
addresses are charged whether in use or idle. Interface endpoints also have
hourly and data-processing costs; by contrast, S3 and DynamoDB gateway
endpoints have no additional charge.
([VPC pricing](https://aws.amazon.com/vpc/pricing/),
[gateway endpoint pricing](https://docs.aws.amazon.com/vpc/latest/privatelink/gateway-endpoints.html)).

Candidates include idle Elastic IPs, NAT gateways with no routes/traffic,
unused interface endpoints, and NAT data processing that might be avoided by
an existing-compatible S3 gateway endpoint. A zero metric window does not prove
network infrastructure is unused; disaster recovery, intermittent deployment,
private DNS, route dependencies, and security architecture must be checked.
Never delete or replace a network resource from the audit.

### AWS KMS

**Read-only evidence.** Use `kms:ListKeys`, `kms:ListAliases`,
`kms:DescribeKey`, `kms:GetKeyRotationStatus`, and, where available,
`kms:GetKeyLastUsage`. Restrict findings to customer-managed keys; AWS-managed
keys have no monthly storage fee.
([KMS authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_kms.html),
[KMS key types](https://docs.aws.amazon.com/kms/latest/developerguide/concepts.html)).

Each customer-managed key costs USD 1/month, prorated hourly; multi-Region
primary and replica keys are each billed, and first/second rotations can add
key-storage cost. Requests can also be billed.
([KMS pricing](https://aws.amazon.com/kms/pricing/)).
Disabled, old, or apparently unused keys remain only candidates because they
may protect retained S3 objects, secrets, logs, or disaster-recovery data.
Deletion requires a complete resource/reference inventory and cryptographic
recovery decision. The audit must never schedule key deletion or disable a key.

### AWS Step Functions

**Read-only evidence.** Use `states:ListStateMachines`,
`states:DescribeStateMachine`, `states:ListExecutions`,
`states:DescribeExecution`, and bounded `states:GetExecutionHistory`. Standard
execution history is retained for 90 days.
([Step Functions authorization reference](https://docs.aws.amazon.com/service-authorization/latest/reference/list_stepfunctions.html),
[execution history quota](https://docs.aws.amazon.com/general/latest/gr/step-functions.html)).

Standard workflows charge per state transition, including retries; Express
workflows charge for requests, duration, and memory. Standard workflows include
4,000 transitions per month in the always-available free tier.
([Step Functions pricing](https://aws.amazon.com/step-functions/pricing/)).
Candidates include unexpected execution growth, retry/redrive loops, failures
that consume transitions/Fargate time without validated output, and schedules
that launch overlapping or redundant work. A failed execution can still have
produced useful idempotent progress, and an infrequently run state machine is
not necessarily obsolete. Changing workflow type is also an architectural
change, not audit remediation. Never update/delete a state machine, execution,
schedule, retry policy, or concurrency from the audit.

## Optional Paid Telemetry to Avoid

The account is small enough that the audit should not create recurring
telemetry costs to discover small savings:

- **S3 Storage Lens advanced metrics/recommendations and CloudWatch publishing.**
  Free Storage Lens metrics are daily and bucket-level; advanced metrics add
  prefix/activity/status-code detail, 15-month history, and CloudWatch
  publishing for an additional charge. Reuse free metrics or an existing free
  export; do not upgrade.
  ([Storage Lens tiers](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage_lens_basics_metrics_recommendations.html)).
- **ECS Container Insights or enhanced observability solely for audit.** It
  produces paid custom metrics/logs. Consume it only where already enabled for
  operational reasons.
- **High-resolution ECS service metrics.** Default service metrics publish at
  60 seconds; the optional 20-second resolution is unnecessary for a weekly
  cost report.
  ([ECS service metrics](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service_utilization.html)).
- **CloudWatch Logs Insights broad scans, metric streams, custom metrics, and
  extra dashboards/alarms created by the audit.** Their own query, ingestion,
  metric, or dashboard charges can eclipse sub-dollar candidates.
- **Cost Explorer hourly granularity or per-resource data retention.** Hourly
  records have an ongoing storage charge, while the weekly audit only needs
  daily/monthly aggregates.
- **New CloudTrail data-event trails, AWS Config recording, IPAM advanced tier,
  or organization-level collectors solely for cost discovery.** If already
  enabled for security/governance, their existing data can corroborate a
  candidate, but the audit must not provision them.

## Minimum Read-Only IAM Surface

The implementation should construct a least-privilege role from the following
actions, narrowed by account, Region, and `edgartools-*` resources where the
service supports resource constraints:

```text
ce:GetCostAndUsage
sts:GetCallerIdentity

s3:ListAllMyBuckets
s3:GetBucketLocation
s3:GetBucketVersioning
s3:GetLifecycleConfiguration
s3:GetEncryptionConfiguration
s3:GetBucketPublicAccessBlock
s3:ListBucketVersions
s3:ListBucketMultipartUploads
s3:ListMultipartUploadParts
s3:ListStorageLensConfigurations
s3:GetStorageLensConfiguration

ecs:ListClusters
ecs:ListServices
ecs:DescribeServices
ecs:ListTasks
ecs:DescribeTasks
ecs:ListTaskDefinitions
ecs:DescribeTaskDefinition

cloudwatch:ListMetrics
cloudwatch:GetMetricData
cloudwatch:DescribeAlarms
logs:DescribeLogGroups
logs:DescribeLogStreams

ecr:DescribeRepositories
ecr:DescribeImages
ecr:ListImages
ecr:GetLifecyclePolicy
ecr:GetLifecyclePolicyPreview
ecr:ListTagsForResource

secretsmanager:ListSecrets
secretsmanager:DescribeSecret
secretsmanager:ListSecretVersionIds

ec2:DescribeNatGateways
ec2:DescribeVpcEndpoints
ec2:DescribeAddresses
ec2:DescribeNetworkInterfaces
ec2:DescribeRouteTables
ec2:DescribeInternetGateways

kms:ListKeys
kms:ListAliases
kms:DescribeKey
kms:GetKeyRotationStatus
kms:GetKeyLastUsage

states:ListStateMachines
states:DescribeStateMachine
states:ListExecutions
states:DescribeExecution
states:GetExecutionHistory
```

Some list/describe APIs cannot be resource-scoped in IAM. The script therefore
must enforce account identity with `sts:GetCallerIdentity`, default to
`us-east-1`, filter inventories to `edgartools-*`, redact secrets and execution
input/output, and never log credentials, secret values, environment variables,
or signed URLs.

Do not include any `Create*`, `Put*`, `Update*`, `Delete*`, `Start*`, `Stop*`,
`Run*`, `Register*`, `Deregister*`, `Abort*`, `Schedule*`, `Tag*`, or
`Untag*` permission. Do not include `secretsmanager:GetSecretValue`,
`kms:Decrypt`, `s3:GetObject` for platform data, or ECR image download actions.
An optional, separately scoped `s3:GetObject` is acceptable only for a known
Storage Lens export prefix that already exists.

## Delay and Confidence Rules

Every finding should carry `observed_at`, `period_start`, `period_end`,
`source`, `source_delay`, `evidence_status`, and `false_positive_notes`.

- Cost Explorer: about 24 hours behind and revisable in the current month;
  preserve its `Estimated` flag and use an exclusive end date.
- S3 CloudWatch storage and Storage Lens: daily, not real-time. Storage Lens
  free console data is queryable for 14 days. Deep list scans are point-in-time
  and may race active writers.
- ECS: stopped-task metadata is guaranteed for only at least one hour. Existing
  CloudWatch metrics must be joined to exact task/run identity; aggregates are
  advisory.
- ECR: last-recorded pull time can lag by up to 24 hours and does not alone
  identify deployed or rollback images.
- Secrets Manager and EC2 inventory are eventually consistent; secret access
  dates are Region-specific and date-resolution.
- Step Functions Standard history expires after 90 days, so absence outside
  that window is not proof of non-use.

For each service use one of these evidence states:

- `confirmed_cost`: billing and resource evidence agree;
- `optimization_candidate`: enough evidence to justify operator review;
- `insufficient_evidence`: permissions, attribution, history, or metrics are
  missing;
- `not_material`: evidence exists but is below the accepted USD 1/month and
  drift thresholds;
- `safety_drift`: configuration or protection drift worth reporting regardless
  of cost.

The script should exit successfully when optional permissions are missing but
must emit `insufficient_evidence`. It should fail only when account identity,
the required Cost Explorer query, output integrity, or read-only invariant
cannot be established.

## Research Conclusion

The first implementation should perform a bounded Cost Explorer query and
metadata audit for all named services, with S3 and Fargate receiving deeper
analysis. It should reuse existing free metrics and existing platform evidence,
avoid enabling paid telemetry, and render every supposed saving as an
Optimization Candidate with explicit uncertainty and remediation prerequisites.
That produces actionable weekly evidence without allowing a reporting job to
become a destructive control plane.
