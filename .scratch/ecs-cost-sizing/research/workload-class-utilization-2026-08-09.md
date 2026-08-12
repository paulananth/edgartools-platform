# Workload-Class ECS Utilization and Fargate Cost Evidence — 2026-08-09

## Question and evidence boundary

For bounded MDM, full-universe MDM, residual-holds/security, `BatchSilver`,
and gold work, what does the repository and its checked-in production evidence
actually establish about CPU, memory, duration, failures/OOMs, and Fargate
vCPU-hour/GB-hour cost?

This report combines repository source, Git history, checked-in operational
evidence, official AWS documentation, and a read-only live AWS audit performed
on 2026-08-09 in account `690839588395`, region `us-east-1`. The live audit
used Step Functions execution history, ECS task results preserved in that
history, CloudWatch Container Insights performance logs, and CloudWatch family
metrics. It did not start or stop work or change any AWS resource.

## Executive finding

The combined evidence supports these workload-level conclusions:

1. **Post-shard `BatchSilver` fits the current medium profile.** A live isolated
   window measured 765 MB peak memory and about 1,556 CPU units while it was on
   large; the later medium/20 run completed 680/680 batches with zero failures,
   with CPU samples at 57–93% of medium's 1,024-unit ceiling. The current source
   correctly routes it to warehouse medium.
2. **Full-universe daily/gold work still justifies warehouse large.** A
   successful daily command reached 1,781 CPU units and 5,972 MiB, while a
   current gold-only refresh was much lighter. The workload contract must
   distinguish the full combined build from standalone `gold-refresh`.
3. **MDM medium is justified for ordinary and full MDM.** The bounded
   backfill reached 913/1,024 CPU units and 1,870 MiB, and the only exact
   full-universe task reached a transient 3,318 MiB on a 4-GiB allocation.
4. **MDM large remains unproven, not disproven.** Its historical successful
   residual run was light, but three immediately preceding 2-GiB attempts were
   OOM-killed between metric samples and the largest intended 13F stage
   processed zero rows. A current 4-GiB versus 8-GiB representative canary is
   still required.

The evidence does **not** yet justify final right-sizing for two cases:

- No full-universe MDM execution exists on the current MDM digest, so the exact
  12.3-hour historical run establishes a memory floor and cost baseline but
  not current resolver throughput.
- Residual-holds proves that 2 GiB was insufficient, but does not distinguish
  today's 4-GiB medium from 8-GiB large under a non-zero 13F workload.

The aggregate family peaks are useful guardrails but cannot be assigned to a
workload when a family serves multiple commands. They also do not provide a
sustained-utilization statistic.

## AWS pricing and metric method

### Pricing basis

The deploy script registers Fargate tasks without `runtimePlatform`, so Fargate
uses its documented defaults of Linux and X86_64. The official Fargate task
definition documentation lists Linux and X86_64 as the defaults:
[Amazon ECS task definition parameters for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html).

AWS says Fargate charges for the **requested** vCPU and memory from image-download
start until termination, rounded to the second, with a one-minute minimum for
Linux. The US East (N. Virginia) Linux/x86 example currently gives:

- `$0.000011244` per vCPU-second = `$0.0404784` per vCPU-hour;
- `$0.000001235` per GB-second = `$0.0044460` per GB-hour.

Sources: [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/), especially
the pricing basis, duration rule, and US East Linux/x86 example. AWS defines GB
as 1024^3 bytes on that page.

For one task:

```text
billable_seconds = max(60, rounded task seconds from image-download start to termination)
compute_cost = billable_seconds *
               (requested_vCPU * 0.000011244 + requested_GB * 0.000001235)
```

For a Distributed Map, cost uses the **sum of every child task's billable
seconds**. Map wall-clock duration divided by concurrency is not a valid cost
calculation.

At the current allocations in
`infra/scripts/deploy-aws-application.sh:1162-1190`:

| Tier | Requested resources | Fargate compute per task-hour |
| --- | --- | ---: |
| small, either runtime | 0.5 vCPU / 1 GiB | `$0.0246852` |
| medium, either runtime | 1 vCPU / 4 GiB | `$0.0582624` |
| large, either runtime | 2 vCPU / 8 GiB | `$0.1165248` |
| historical MDM medium used by the July 25 full run | 1 vCPU / 2 GiB | `$0.0493704` |

These figures exclude Step Functions transitions, public IPv4, CloudWatch,
data transfer, S3, Snowflake/Postgres, and other charges. AWS explicitly lists
CloudWatch, public IPv4, and data transfer as additional charges on the Fargate
pricing page. Refresh the rates before making a production savings commitment.

### Metric interpretation

AWS documents `CpuUtilized` as CPU units used and `MemoryUtilized` as megabytes
used. Both support the dimension set `TaskDefinitionFamily`, `ClusterName`, and
`TaskId`; this is the dimension set required to bind a workload to a task:
[Amazon ECS Container Insights metrics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-enhanced-observability-metrics-ECS.html).
The underlying performance log event also contains `TaskId`,
`TaskDefinitionFamily`, `TaskDefinitionRevision`, image, reservations, and
utilization, making it the preferred durable evidence source:
[Container Insights performance log events](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-reference-performance-logs-ECS.html).

The existing historical query used one-hour periods and only the
`TaskDefinitionFamily` dimension
(`.scratch/ecs-cost-sizing/history-right-sizing-2026-08-09.md:3-14`). Its maxima
are valid family-level warning signals, but they do not identify the command,
revision, image, task, or sustained duty cycle.

## Current deployed identity and aggregate guardrails

The post-handoff baseline binds all 26 state machines to the current six
profiles and immutable image digests
(`.scratch/ecs-cost-sizing/post-handoff-baseline-2026-08-09.md:25-48`):

| Runtime tier | Current revision | Current immutable digest |
| --- | --- | --- |
| warehouse small / medium / large | `small:166`, `medium:170`, `large:163` | `sha256:86f511031d3fdf790f44d4308bb40157d97adbfd2c1b9fdcd4a9755d1e81c625` |
| MDM small / medium / large | `mdm-small:143`, `mdm-medium:143`, `mdm-large:77` | `sha256:9f55a0a7910cb55d1a88190c7642ccfc55b6c4f0210deccb956f6750c3711de2` |

The 2026-07-10 through 2026-08-10 family-level query recorded
(`.scratch/ecs-cost-sizing/history-right-sizing-2026-08-09.md:16-25`):

| Family | Metric points | Maximum CPU | Maximum memory | What it can establish |
| --- | ---: | ---: | ---: | --- |
| warehouse small | 0 | none | none | No sizing evidence. |
| warehouse medium | 193 | 1,024 / 1,024 (100%) | 3,934 / 4,096 MiB (96%) | At least one medium workload reached both boundaries; no global downsize. |
| warehouse large | 101 | 2,002 / 2,048 (98%) | 5,972 / 8,192 MiB (73%) | At least one large workload was CPU-bound; workload identity is unknown. |
| MDM small | 22 | 512 / 512 (100%) | 166 / 1,024 MiB (16%) | Memory has room, but CPU saturated in at least one sample. |
| MDM medium | 70 | 918 / 1,024 (90%) | 3,318 / 4,096 MiB (81%) | At least one MDM-medium workload approached both limits. |
| MDM large | 6 | 529 / 2,048 (26%) | 380 / 8,192 MiB (5%) | Sparse low-use samples; not proof the residual workload is over-sized. |

No average, p50, p95, duty-cycle-above-threshold, or exact task-to-command
join is preserved in that artifact. Therefore none of these rows is a complete
answer to the ticket's “peak and sustained by workload class” question.

## Read-only live AWS measurements

### Method and limitations

For ordinary ECS tasks, Step Functions' preserved ECS result supplied the
exact task ID, task-definition ARN, image digest, command, requested resources,
exit code, `PullStartedAt`, and `StoppedAt`. Billable seconds use the documented
Linux minimum and are rounded up from that pull-to-stop interval.

Container Insights performance log events with `Type = "Task"` supplied
one-minute task-level CPU units and memory MiB. `cpuAvg` and `memoryAvg` below
are averages over observed one-minute points, not averages over every second;
short tasks have only one or two samples. A low sampled memory maximum cannot
invalidate an ECS exit 137 because a short allocation spike can occur between
samples.

For the Distributed Map, the live audit fetched all child execution start/stop
times but did not issue 680 separate history calls. Its resource-hours and cost
therefore use summed child **execution wall time**, which includes Step
Functions/ECS lifecycle overhead and is an upper-bound estimate rather than
exact Fargate billing.

### Bounded MDM on the current image

Execution prefix `aws-mdm-e2e-1786310173` ran all six commands successfully on
current digest `sha256:9f55a0a7...1de2`, using `mdm-small:143` and
`mdm-medium:143`:

| Command | Tier | Billed seconds | CPU peak / average | Memory peak / average |
| --- | --- | ---: | ---: | ---: |
| `mdm migrate` | small | 72 | 256 / 140 units | 126 / 74 MiB |
| `mdm run --entity-type all --limit 5` | medium | 102 | 468 / 381 | 334 / 274 MiB |
| `mdm backfill-relationships --limit 100` | medium | 467 | 913 / 177 | 1,870 / 495 MiB |
| `mdm sync-graph --limit 100` | medium | 73 | 452 / 452 (one point) | 41 / 41 MiB |
| `mdm verify-graph` | small | 259 | 173 / 35 | 163 / 123 MiB |
| `mdm counts` | small | 60 minimum | 256 / 256 (one point) | 24 / 24 MiB |

The chain consumed 0.233 requested vCPU-hours and 0.822 requested GB-hours,
approximately `$0.0131` of Fargate compute. Even this bounded backfill reached
89% of medium CPU; bounded input is not evidence that all MDM stages belong on
small.

### Full and partially bounded MDM

The exact no-limit task in
`bronze-seed-silver-gold-1786226258` used `mdm-medium:138`, digest
`sha256:cc64ba85...4640a`, and exited 0 after 44,227 billable seconds
(12h17m). Its 737 one-minute points measured:

- CPU peak 581/1,024 (57%), average 96 (9%), p95 168 (16%);
- memory peak 3,318/4,096 MiB (81%), average 525 MiB (13%), p95 555 MiB;
- 12.285 vCPU-hours and 49.141 GB-hours, about `$0.7158` compute.

The large separation between memory p95 and peak is a transient-spike warning,
not evidence for a downgrade. This task used the pre-handoff MDM image and does
not measure the current resolver implementation.

For comparison, `mdm-run-perf-measure-1786282750` processed a bounded 2,000
rows on `mdm-medium:140`, digest `sha256:6a38edf1...107b`, in 1,315 billable
seconds. It peaked at 286 CPU units and 659 MiB, averaging 81 CPU units and
408 MiB. That is 0.365 vCPU-hours and 1.461 GB-hours, approximately `$0.0213`.
The different image and limit prevent linear extrapolation to current full
universe work.

### Residual-holds/security

`residual-holds-20260725T221723Z` made three attempts on historical
`mdm-medium:66` (1 vCPU/2 GiB); all exited 137 after 60-68 billable seconds.
The five-minute family metric reported only 176 MiB maximum, directly proving
that coarse sampled metrics can miss the fatal allocation spike.

The replacement `residual-holds-20260725T222735Z` used `mdm-large:1`
(2 vCPU/8 GiB). After one image-pull failure, eight heavy large-profile stages
completed with 4,274 aggregate billable seconds: 2.374 vCPU-hours, 9.498
GB-hours, and approximately `$0.1383` compute. Fifteen five-minute family
buckets measured CPU peak 529/2,048 (26%) and mean-of-bucket averages 170
(8%); memory peaked at 380/8,192 MiB (5%) and averaged 223 MiB (3%).

Those low values are real for that run but not representative proof: the 13F
relationship stage produced zero rows, while the preceding 2-GiB run OOMed.
The evidence supports testing 4 GiB, not deleting the 8-GiB fallback.

### BatchSilver profile/concurrency comparison

All compared runs used warehouse digest `sha256:a493e0d1...e504e`:

| Map | Profile | Result | Wall time | CPU peak / avg / p95 | Memory peak / avg / p95 |
| --- | --- | --- | ---: | ---: | ---: |
| `medium-20-retry` | `medium:160`, concurrency 20 | 680/680 succeeded | 52m06s | 1,024 / 468 / 946 | 729 / 131 / 402 MiB |
| `mc16-test` | `large:153`, concurrency 16 | 216 succeeded, 1 failed, 15 aborted, 448 pending | 22m04s before failure | 982 / 406 / 896 | 440 / 115 / 347 MiB |
| `shard-aware` | `large:153`, concurrency 4 | 240 succeeded, 4 aborted by operator | 1h32m56s observed | 1,814 / 467 / 988 | 909 / 142 / 511 MiB |

The large/16 failure was `ECS.AmazonECSException`: 16 tasks requested 32 vCPUs
against the account's 30-vCPU concurrent quota. Medium/20 stayed at 20 vCPUs
and completed every item. Its 680 child executions summed to 61,245 seconds,
an upper bound of 17.013 vCPU-hours, 68.050 GB-hours, and about `$0.9912`.
The partial large/16 run had already consumed an upper-bound 11.661 vCPU-hours,
46.644 GB-hours, or `$0.6794`, without producing a complete map.

This is decisive production evidence for the current medium/concurrency pair.

### Gold and combined daily/gold work

Current-image execution `gold-refresh-stage15-1786285678` used `large:160`,
digest `sha256:86f51103...c625`, exited 0, and consumed 151 billable seconds.
Its three points measured CPU peak 1,266/2,048 (62%), average 856 (42%),
memory peak 1,827/8,192 MiB (22%), and average 1,044 MiB (13%). That is 0.084
vCPU-hours, 0.336 GB-hours, or approximately `$0.0049`.

An earlier gold-only execution on `large:110` took 209 billable seconds and
peaked at 1,031 CPU units and 2,709 MiB, costing approximately `$0.0068`.
These two gold-only runs are candidates for a medium-profile canary; they do
not establish that the full combined gold path fits medium.

The successful full `daily-incremental-ticket89-unblocked-1785856213` warehouse
command used `large:120`, ran 9,549 billable seconds (2h39m), and measured 159
one-minute points: CPU peak 1,781 (87%), average 712 (35%); memory peak 5,972
MiB (73%), average 3,353 MiB (41%). The main command alone consumed 5.305
vCPU-hours and 21.220 GB-hours, approximately `$0.3091`. This is the strongest
execution-bound reason to retain warehouse large for the combined
daily/full-universe workload.

## Workload-class findings

### 1. Bounded MDM

**Current shape.** The operator script defines a bounded AWS-only chain with
`mdm run --limit 5`, backfill/sync `--limit 100`, migration, verification, and
counts (`infra/scripts/run-aws-mdm-e2e.sh:15-24,43-50,219-229`). The current
post-handoff cohort records all six commands on `mdm-small:143` or
`mdm-medium:143`, current digest `sha256:9f55...1de2`, with exit code 0
(`.scratch/ecs-cost-sizing/post-handoff-baseline-2026-08-09.md:91-107`).

**Measured facts.** Correctness completion is proven for this bounded command
set and exact digest. The checked-in baseline did not include task metrics; the
read-only live audit above now supplies exact task IDs, durations, utilization,
and requested resource-hours.

**Cost.** The six tasks cost approximately `$0.0131` from their preserved
image-pull-to-stop intervals. The helper omits `mdm export`, so this remains a
bounded validation-chain measurement rather than publication-chain cost.

**Failure/OOM evidence.** No OOM is recorded for this current bounded cohort.
Exit 0 does not prove full-universe safety.

**Remaining evidence.** Preserve selected/processed record counters and an
export stage before interpreting this as cost per published record.

### 2. Full-universe MDM

**Current shape.** The full `bronze_seed_silver_gold` chain has an explicit
no-limit invariant and routes `mdm run --entity-type all`, backfill, export,
and graph sync to MDM medium; verification uses MDM small
(`infra/scripts/deploy-aws-application.sh:3992-4015`). Current MDM medium is
1 vCPU/4 GiB.

**Best exact historical timing.** The checked-in Ticket 20 completion package
binds execution
`ticket20-strict-endpoint-seal-850ea34-20260725T130457Z` to commit `850ea347`,
MDM image digest `sha256:c1b0...00f1`, and `mdm-medium:58`
(`docs/release-readiness/ticket20-completion-evidence-2026-07-25.json:23-55`).
Its stage timings include:

- `StrictMdmRun`: 4.70 hours, succeeded;
- backfill: 1.3 minutes; repeat/idempotency backfill: 1.3 minutes;
- export: 16.4 minutes;
- sync: 1.3 minutes; repeat sync: 1.2 minutes;
- candidate verify/activate/active verify: 1.4/1.2/4.4 minutes.

Source: `docs/release-readiness/ticket20-completion-evidence-2026-07-25.json:57-69`.
Git inspection of that exact deployment commit shows `mdm-medium` was then
1 vCPU/2 GiB. At current US East rates, the 4.70-hour `StrictMdmRun` alone is
approximately `$0.2320`; all listed ECS MDM stages plus the historical
2-vCPU/4-GiB gold stage total approximately `$0.2577`. These are reconstructed
compute estimates from stage durations, not Cost Explorer charges, and do not
include retries or non-Fargate services.

**Why this is not a current benchmark.** Current code later parallelized company,
security, and person resolution and raised default resolver concurrency to 16.
The repository records a 62,190-company sequential baseline of about 2.16
seconds/row (~37 hours projected), but explicitly says current per-domain live
durations remain unmeasured
(`.scratch/mdm-run-throughput/map.md:20-41`; Git commits `e244a5712f65` and its
predecessor PR #376). The live audit tied the 81% memory maximum to the older
no-limit execution, but no current-digest full-universe run exists.

**Failure/OOM evidence.** The exact Ticket 20 full run succeeded. Separate
historical and rollback evidence contains correctness and resumability failures,
but no current full-universe OOM on 4 GiB is established locally.

**Remaining evidence.** A fresh current-digest, full-universe run must
record domain row counts and durations separately for company, adviser, fund,
security, person, and relationship stages; task-level peak/sustained metrics;
DB retry/pool pressure; output/idempotency checks; and task-billed seconds. The
older 4.70-hour result must not be used as the current runtime baseline.

### 3. Residual-holds and full-universe security

**Current shape.** The state machine routes eight heavy stages—security,
person, four relationship derivations, export, and full graph sync—to
`mdm-large` (2 vCPU/8 GiB), then verifies on MDM small
(`infra/scripts/deploy-aws-application.sh:4593-4705`; stages are summarized in
`docs/release-readiness/residual-holds-graph-pipeline.md:23-45`). It is the only
production state machine that references MDM large
(`.scratch/ecs-cost-sizing/post-handoff-baseline-2026-08-09.md:43-48`).

**Hard lower-bound evidence.** Execution
`residual-holds-20260725T221723Z` OOM-killed in `MdmSecurities` with exit 137 on
the old 1-vCPU/2-GiB MDM medium task. The repository attributes it to loading
full-universe holdings/ownership surfaces and introduced 2-vCPU/8-GiB
`mdm-large` in Git commit `9bac02d860c0`
(`docs/release-readiness/residual-holds-graph-pipeline.md:47-55`). This proves
2 GiB is unsafe for that old path. It does **not** distinguish 4 GiB from 8 GiB.

**Successful heavy-stage evidence.** The fresh 8-GiB execution
`residual-holds-20260725T222735Z` completed all heavy stages and failed only at
verification because the state machine built a partial candidate but verified
the active generation (`docs/release-readiness/residual-holds-status-2026-07-26.md:3-23,61-74`).
A later one-off full sync and verify produced 193,323 nodes and 166,067 edges
with exact parity (`...residual-holds-status-2026-07-26.md:76-101`).

**Representativeness defect.** `MdmInstitutionalHolds` reported success but
created zero rows because `sec_thirteenf_filing` was absent from the sharded
reader allowlist, even though the 13F holding source contained 6.8 million rows
(`...residual-holds-status-2026-07-26.md:114-133`). Therefore this run did not
exercise the intended largest relationship workload and cannot establish its
memory requirement.

**Utilization and cost.** The live execution window binds the family maxima of
529 CPU units and 380 MiB to the heavy run. Its eight successful large stages
cost approximately `$0.1383`; this excludes the failed image pull and three
small-profile verification attempts.

**Remaining evidence.** Run a representative current-image canary on
today's 4-GiB MDM medium for security plus residual relationship processing,
including non-zero 13F records, and compare it with large. Capture each stage's
records, task ID, duration, max/p95/average CPU and memory, retries/OOMs, graph
parity, and cost. This is the required discriminator before removing
`mdm-large`.

### 4. BatchSilver

**Current shape.** Post-shard `BatchSilver` runs one shard per task on warehouse
medium (1 vCPU/4 GiB), with `MaxConcurrency=20`
(`infra/scripts/deploy-aws-application.sh:3897-3923`).

**Execution-bound utilization.** In production execution
`bronze-seed-silver-gold-shard-aware-1786206602`, while the same post-shard
workload was temporarily on large, a 60-minute Container Insights window
recorded:

- peak memory 765 MB / 8,192 MB (9%); typical one-minute peaks 100–670 MB;
- peak CPU about 1,556 / 2,048 units (76%).

Source:
`.scratch/pipeline-throughput-architecture/issues/13-decide-batchsilver-task-sizing.md:13-31`.
This is the strongest workload-specific resource measurement in the local
evidence.

**Current medium result.** Git commit `fd5e18d3b4fe` and the current source
record that large/16 failed after 216/680 successful items because 32 requested
vCPUs exceeded the account's 30-vCPU quota—not because of memory. Medium/20 then
completed 680/680 with zero failures at about 4.6 seconds of stage wall-clock
per batch; medium CPU samples ran at 57–93% of its ceiling
(`infra/scripts/deploy-aws-application.sh:3902-3920`). This validates the
current profile/concurrency pair for that execution.

**Task duration and cost sample.** One 14-CIK, 238-MB-shard child from
`bronze-seed-silver-gold-medium-20-retry-1786214600`, task
`12ccb0199ee141eb9a6b6597d52163dc`, took 77.4 seconds end to end. Of that,
about 46 seconds were provisioning, image pull, and teardown; hydrate was 11.3
seconds and publish 3.2 seconds
(`.scratch/pipeline-throughput-architecture/issues/11-profile-batchsilver-per-batch-merge-overhead.md:80-109`).
At the current medium rate this sampled task costs about `$0.001253`.

If all 680 tasks had exactly that billed duration, compute would be about
`$0.852`; that is a **sensitivity estimate only**, because shard sizes, CIK
counts, retries, and task durations vary. The exact map cost requires summing
all 680 stopped-task billing intervals. The 4.6-second effective stage rate
must not be multiplied by one task's hourly rate.

**Failure/OOM evidence.** The earlier pre-shard monolithic path OOM-killed on
4 GiB, but that mechanism disappeared when each task moved to one 80–800 MB
shard. No post-shard OOM is recorded. The large/16 failure was a quota failure.

**Remaining evidence gap.** The live audit now supplies current-medium peak and
p95 utilization, child duration distribution, summed child wall time, exact
digest/revision, and success counts. Exact Fargate cost still requires every
child's pull-to-stop interval rather than child execution wall time, and these
measurements should be persisted in an immutable release manifest.

### 5. Gold

**Current shape.** Full-universe gold-affecting work and `gold-refresh` route to
warehouse large (2 vCPU/8 GiB)
(`infra/scripts/deploy-aws-application.sh:1168-1176,4011-4015`).

**OOM floor and recovery.** `daily-incremental-1785336584` OOM-killed four
attempts at 4 GiB while building `sec_thirteenf_holding` after prior gold tables
remained resident. The fix combined table-at-a-time streaming with an 8-GiB
large profile. A fresh bootstrap on `large:90`, immutable digest
`sha256:aca8078c...b30`, then completed all 28 tables, including 6,799,919 13F
holding rows; a daily run also completed its 3h20m warehouse command without
OOM (`.scratch/gold-build-memory-reliability/issues/03-decide-task-memory-fix-to-unblock-daily-incremental.md:144-171`).

This proves the **combined** fix works. It does not prove that current streaming
still needs 8 GiB: the repository explicitly notes that streaming and the
memory bump were deployed together, so isolated peak-memory reduction was not
measured.

**Gold-only duration.** A live `gold-refresh` on the 2-vCPU/8-GiB profile,
`ticket07-profile-gold-refresh-1785757940`, had a 169.12-second container
lifetime. It spent 13.78 seconds hydrating 1,021.9 MB of silver, 55.77 seconds
building 27 tables, 60.65 seconds in a then-unconditional no-op silver publish,
and 31.34 seconds in container lifecycle overhead
(`.scratch/pipeline-throughput-architecture/issues/07-profile-gold-refresh-stage-breakdown.md:32-57`).
At the current large rate, that historical run's Fargate compute is about
`$0.00547`.

**Current-code caveat.** Git commit `836d9049ddcf` subsequently added a
protected-table fingerprint and skips that provably unchanged publish;
`edgar_warehouse/application/warehouse_orchestrator.py:873-991` contains the
current implementation. Therefore 169.12 seconds and `$0.00547` overstate
today's expected gold-only duration/cost. Subtracting 60.65 seconds would be a
projection, not a measured current result.

**Utilization result.** The live audit now binds current gold-only utilization
and cost, and separately binds the 5,972-MiB family maximum to a successful
combined daily/full-universe task. Standalone gold is eligible for a medium
canary; the combined daily path is not.

## Remaining experiments after this research ticket

The available historical and live evidence resolves what can be measured
without launching new production work. Future telemetry should preserve one
row per task/attempt with:

1. workload class, state-machine execution/state, command, limits, records
   selected/attempted/committed/exported, and output identity;
2. task ARN/ID, task-definition family and revision, immutable image digest,
   launch type/architecture, start/pull/stop times, stop reason, exit code, and
   retry ordinal;
3. an exact Container Insights window using `TaskId` plus family/cluster,
   including max, average, p50/p95 where available, and time above 70/80/90% for
   CPU and memory;
4. requested vCPU/GB-hours and Fargate compute cost from the sum of billed task
   seconds, with Step Functions and other service costs reported separately;
5. success/OOM/quota/retry classification and correctness/idempotency gates.

The remaining new-execution coverage is:

- one current-digest full-universe MDM execution, split by entity type;
- residual security/holds on medium and large with non-zero 13F processing;
- one bounded medium canary for the standalone gold stage.

These are inputs to canary and sizing decisions, not blockers to this research
finding. The defensible interim policy is: keep `BatchSilver` on medium at
concurrency 20; retain warehouse large for combined daily/full-universe work;
retain MDM medium for ordinary and full-universe MDM; make standalone gold
eligible for a medium canary; and treat MDM large as a removal candidate, not a
proven need or a safe removal.

## Primary sources consulted

Repository evidence:

- `infra/scripts/deploy-aws-application.sh` and Git history, especially commits
  `9bac02d860c0`, `4760be81bfdf`, `836d9049ddcf`, `fd5e18d3b4fe`, and
  `e244a5712f65`.
- `infra/scripts/run-aws-mdm-e2e.sh`.
- `.scratch/ecs-cost-sizing/history-right-sizing-2026-08-09.md`.
- `.scratch/ecs-cost-sizing/post-handoff-baseline-2026-08-09.md`.
- `.scratch/pipeline-throughput-architecture/issues/07-profile-gold-refresh-stage-breakdown.md`.
- `.scratch/pipeline-throughput-architecture/issues/11-profile-batchsilver-per-batch-merge-overhead.md`.
- `.scratch/pipeline-throughput-architecture/issues/13-decide-batchsilver-task-sizing.md`.
- `.scratch/gold-build-memory-reliability/issues/03-decide-task-memory-fix-to-unblock-daily-incremental.md`.
- `.scratch/mdm-run-throughput/map.md`.
- `docs/release-readiness/ticket20-completion-evidence-2026-07-25.json`.
- `docs/release-readiness/residual-holds-graph-pipeline.md`.
- `docs/release-readiness/residual-holds-status-2026-07-26.md`.

Official AWS sources:

- [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/).
- [Amazon ECS task definition parameters for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html).
- [Amazon ECS Container Insights metrics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-enhanced-observability-metrics-ECS.html).
- [Container Insights performance log events for Amazon ECS](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Container-Insights-reference-performance-logs-ECS.html).
