# Measure ECS Utilization by Workload Class

Type: research
Status: resolved
Blocked by: 01

## Question

For each workload class, what are peak and sustained CPU, memory, duration,
failure/OOM, and Fargate vCPU-hour/GB-hour measurements? Separate bounded MDM,
full-universe MDM, residual-holds/security, BatchSilver, and gold work. Bind
evidence to executions, revisions, image digests, and metric windows.

## Resolution

A read-only, task-bound AWS audit measured the representative workload classes
and bound results to executions, task-definition revisions, immutable image
digests, and Container Insights windows. No production workload was launched or
changed.

- Bounded MDM cost about `$0.0131` across six successful tasks. Medium remains
  justified: the bounded backfill reached 913/1024 CPU units and 1,870/4,096
  MiB.
- An older no-limit full-universe MDM run succeeded on medium in 12h17m for
  about `$0.7158`, with a transient 3,318/4,096-MiB maximum. A current-digest
  full-universe run is still needed before any downgrade.
- Residual security/holds failed three times with exit 137 on the historical
  2-GiB medium profile. Its 8-GiB replacement succeeded, but processed zero
  institutional-hold rows because of a source defect, so MDM large is a canary
  candidate rather than a safe removal.
- BatchSilver medium at concurrency 20 completed 680/680 items in 52m06s. The
  large/concurrency-16 trial failed on the account's concurrent-vCPU quota.
  Keep BatchSilver on medium/20.
- Current standalone gold completed on large in 151 billable seconds and is a
  medium-canary candidate. A successful combined daily/full-universe task used
  up to 1,781/2,048 CPU units and 5,972/8,192 MiB, so that combined path should
  retain large.

The detailed measurements, assumptions, costs, and remaining canaries are in
[`../research/workload-class-utilization-2026-08-09.md`](../research/workload-class-utilization-2026-08-09.md).
