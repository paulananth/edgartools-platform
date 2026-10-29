# Cost-effective compute for configured data pipelines

Research note for the timed-pipeline-operations workstream. Official AWS documentation was consulted on 2026-10-29. This is architecture guidance, not a deployment decision or a runtime benchmark. Repository contracts below are grounded in current skills/specifications; recommendations are proposals.

## Recommendation

**Proposal:** Preserve one portable pipeline contract and the existing execution boundary. Keep local Docker as the contract qualification path and ECS/Fargate as the first AWS execution target, with resource profiles and concurrency supplied by configuration. Let Bookkeeping own run/work state, leases, attempts, checkpoints and recovery; let Change Journal own immutable events and delivery receipts. Existing control should coalesce overlapping schedule/manual triggers onto the same run/work identities. Do not add a queue or a second state store.

Treat HPC as a measured execution profile, not a separate pipeline architecture. Start with ordinary CPU/memory containers. Consider AWS Batch with EC2/Spot only if measured throughput, concurrency, per-task economics, special hardware, or capacity requirements justify its additional compute-environment and queue operations. GPUs and MPI are unnecessary for ordinary parsing, validation, joins and database-backed mastering unless profiling establishes a suitable parallel numerical kernel or distributed-memory algorithm.

## Why ECS/Fargate first

**AWS fact:** Fargate is a managed container runtime where CPU and memory are specified per task; AWS documents per-second billing with a minimum charge, and discrete supported CPU/memory combinations. This makes it a low-operations baseline, while task sizing still matters because billing follows allocated resources. [Fargate pricing and selection](https://docs.aws.amazon.com/decision-guides/latest/decision-guides/fargate-or-lambda.html), [Fargate task sizing](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-cpu-memory-error.html)

**AWS fact:** AWS Batch can manage either Fargate or EC2 capacity, offers queues and retry policy, and Batch-managed environments create/control resources on the user's behalf. Batch on Fargate remains Fargate compute; it adds job scheduling semantics and does not inherently make each job faster or cheaper. [Batch components](https://docs.aws.amazon.com/batch/latest/userguide/batch_components.html), [managed environments](https://docs.aws.amazon.com/batch/latest/userguide/managed_compute_environments.html), [Batch retries](https://docs.aws.amazon.com/batch/latest/userguide/job_retries.html)

**Proposal:** Do not add Batch merely to schedule existing independent Bookkeeping work items. It is justified when AWS-side queueing/capacity management materially solves an observed operational problem, or EC2/Spot economics and packing materially beat Fargate after accounting for idle capacity, startup, retry waste and operator overhead. Keep Bookkeeping authoritative if Batch is later used as a compute adapter: Batch job state is execution detail, not a competing pipeline ledger.

## Cost and performance controls

- **Right-size from evidence.** Record task CPU, memory high-water, duration, startup, artifact bytes read/written, retry count and completed units for representative workloads. Tune each configured worker profile against throughput and correctness, not CPU average alone; preserve memory headroom for skewed/high-cardinality inputs. ECS service utilization metrics are published for services, but standalone tasks are not the same resource shape; the AWS Compute Optimizer supported-resource list currently names ECS services on Fargate, not arbitrary standalone ECS tasks. Do not assume a standalone-task recommendation exists. [ECS utilization metrics](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service_utilization.html), [Compute Optimizer supported resources](https://docs.aws.amazon.com/compute-optimizer/latest/ug/supported-resources.html)
- **Bound concurrency at the control boundary.** Configure global and per-profile limits, then set work-unit granularity so each unit's compute is worthwhile relative to container/task startup and control round trips. Current operations already exposes reader/bundle/window controls; Bookkeeping has leases, bounded retries, per-unit identities and independent work completion. This is a configuration tuning direction, not a new concurrency service. [Data operations load contract](../../../../skills/data-operations/SKILL.md), [Bookkeeping spec](../../../../skills/bookkeeping/SPEC.md)
- **Batch work at useful boundaries.** Amortize initialization, image pull, parsing setup and database round trips by grouping small artifacts, while keeping units independently retryable and bounded in memory. Oversized bundles amplify retry cost and memory pressure. Compare end-to-end cost per verified unit, including input preparation, artifact transfer, destination commit and verification; faster parsing alone may not improve wall-clock completion when storage or database contention dominates.
- **Reduce data motion.** Keep compute near its S3 inputs and outputs in the same AWS Region where feasible; AWS documents this as reducing latency and transfer costs. Avoid repeatedly copying large intermediates between units; pass immutable, content-addressed artifact references and hashes under existing contracts. [S3 performance guidance](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-guidelines.html)
- **Use a falsifiable scorecard.** Compare the same frozen input and rules digest across local Docker and AWS. Report verified records/units per elapsed minute, total allocated vCPU-seconds and memory-seconds, bytes transferred, retries/rework, peak memory, correctness parity, and operational cost from billing data when available. This research contains no benchmark result.

## ARM64 portability

**AWS fact:** ECS supports Linux ARM64 on Fargate and EC2; Fargate requires a supported platform version. Batch Fargate also supports ARM64 job definitions. [ECS ARM64](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-arm64.html), [Batch Fargate](https://docs.aws.amazon.com/batch/latest/userguide/fargate.html)

**Proposal:** Build and qualify both x86_64 and ARM64 images only where imported native wheels and runtime dependencies are available for both architectures. For Python/Rust packages, verify wheel tags, native extension loading, parser parity and throughput on each target; do not infer portability from a successful multi-arch container build. Keep the same interface, data contract, rules digest, receipts and recovery semantics in local Docker and AWS. Select architecture by measured cost per verified unit, including any wheel fallback/build cost and image size.

## Spot economics and recovery

**AWS fact:** Fargate Spot uses spare capacity, can be unavailable/delayed, and sends an interruption warning before stopping a task. EC2 Spot also has interruption warnings and fluctuating availability/prices. A warning is not a durability guarantee. [ECS Fargate Spot](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-capacity-providers.html), [EC2 interruption notices](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-instance-termination-notices.html)

**Proposal:** Model retry-adjusted cost, not the advertised discount: expected successful work cost includes lost work since the last durable checkpoint, restart/setup cost, unavailable-capacity delay and repeat verification. Spot is attractive for independently resumable, idempotent units with durable outputs and short recovery distance. Keep correctness-critical or latency-bound work on on-demand capacity unless observed interruption economics support Spot. Bookkeeping lease fencing and checkpoints plus Change Journal idempotent receipts are the recovery mechanisms; worker SIGTERM handling may flush safe local state, but must never claim completion without normal verifier/readback admission.

## Performance diagnosis and escalation

Collect per-stage duration, queue/wait time, task startup, CPU, peak memory, I/O bytes, database wait/lock indicators, units per worker and retry reasons. Compare profiles on the same bounded representative cohort, then run the full qualification path after choosing a candidate. Use failure isolation by unit and stage; report the failing unit and preserve unaffected work. For recurring regressions, perform a five-whys root-cause analysis and route fixes to the owning source, worker, storage or control skill. Do not increase concurrency to hide a bottleneck; it can worsen database contention or throttling.

Escalate beyond ordinary containers only on evidence:

| Option | Consider when | Avoid when |
| --- | --- | --- |
| AWS Batch / EC2 | Demonstrated high throughput/concurrency, special instance requirements, or repeatable task-level savings after retry and idle-capacity costs | The current load fits bounded Fargate workers and no queue/capacity problem is evidenced |
| GPU | A measured GPU-capable numeric/ML kernel dominates runtime and end-to-end transfer/launch overhead still yields benefit | Parsing, joins, validation, database I/O or ordinary ETL dominate |
| MPI/distributed HPC | A workload has a naturally partitioned distributed-memory algorithm with sufficiently large compute per communication phase | Independent files/units can already be parallelized as bounded workers, or shared database writes are the bottleneck |

AWS Batch's own guidance positions EC2 where specific instance types, GPUs, higher throughput/concurrency or custom host control are needed; Fargate is the simpler choice for suitable jobs. This supports an evidence-gated escalation, not an HPC-first design. [Batch compute choice](https://docs.aws.amazon.com/batch/latest/userguide/bestpractice4.html)

## Production-support diagnosis boundary

The production-support trigger warrants coordinated expertise from architecture and security owners before changing execution policy, credentials, permissions, network boundaries or workload placement. Begin with read-only evidence: the frozen pipeline/rules/runtime identities, Bookkeeping status and lease authority, Change Journal receipts, task logs/metrics, image digest, and destination verification. Reproduce locally against retained fixtures where possible. The architecture review should identify the bottleneck and least-complex remedy; security review should verify task role, execution role, secret scope, network paths, artifact access and separation of worker/verifier duties. Any permission or production runtime change remains an operator-approved change supported by that evidence.

## Limits and unresolved checks

- No live account, quota, price, deployment, provider documentation endpoint or runtime workload was queried. Quotas, region/architecture availability and pricing change; check the selected region/account and current AWS price source before a deployment or cost estimate. Avoid embedding service limits or prices in the contract.
- Compute Optimizer documentation lists ECS Fargate **services** among supported resources. It does not establish recommendation support for standalone ECS tasks. Verify the current API/resource scope if a future workload uses ECS services or if AWS expands support; meanwhile use task-level telemetry and controlled measurement.
- The Fargate-versus-Batch recommendation is an initial architecture proposal. Actual worker runtimes, data sizes, contention, retry frequency, image pull times and on-demand/Spot prices are unmeasured here.

## Repository evidence consulted

- `skills/data-operations/SKILL.md` and `RUNBOOK.md`: configured load controls, run recovery and operational ownership.
- `skills/bookkeeping/SPEC.md` and `DESIGN.md`: task protocol, state/lease/recovery boundaries and external workers.
- `skills/change-journal/SPEC.md`: immutable event and delivery-receipt ownership.
- `skills/aws-snowflake-operations/SKILL.md`: AWS deployment boundary and retired legacy pipeline paths.
