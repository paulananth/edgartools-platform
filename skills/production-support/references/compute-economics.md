# Cost-effective high-performance execution

Optimize total cost of verified work subject to its configured deadline and
correctness. Faster parsing alone is not a saving when I/O, destination commits,
startup or repeat verification dominate. Preserve retention, security, recovery
and verification requirements while reducing waste.

## Measure the limiting stage

For the same frozen inputs/rules/runtime, compare queue/startup and per-stage
time, verified units per elapsed minute, CPU allocation/utilization, memory peak
and headroom, bytes transferred, storage/database waits, retries and interruption
loss. State measurement coverage and confidence. Compare total cost per completed
workload or verified unit, including allocated CPU/memory, storage, transfer,
telemetry, startup, idle capacity, failed attempts and operating overhead. Use
current regional pricing or billing; label estimates and assumptions explicitly.

Try configured right sizing, useful batching and bounded concurrency first.
Preserve memory headroom for skew; larger bundles increase retry waste. Increase
workers only while throughput improves within downstream capacity. Keep compute
near durable artifacts and pass references instead of copying intermediates.
AWS recommends stage-specific cost/performance configurations and evaluating the
cost of shortened runtime against parallel efficiency:
[HPC cost principles](https://docs.aws.amazon.com/wellarchitected/latest/high-performance-computing-lens/design-principles-cost.html).

## Select compute on evidence

Start with qualified containers on existing ECS/Fargate infrastructure and local
Docker. Escalate to Batch/EC2 when measured capacity/packing, throughput or special
hardware needs justify its additional operating cost. Batch on Fargate adds job
management, not inherently cheaper compute. GPU or MPI needs a measured suitable
kernel/algorithm and end-to-end gain; ordinary file parallelism is not that proof.
[Batch compute choice](https://docs.aws.amazon.com/batch/latest/userguide/bestpractice4.html).

Compare ARM64 and x86_64 only after native dependencies, image startup and
correctness/performance are qualified on both. A multi-architecture build is not
behavioral parity. [ECS ARM64](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-arm64.html).

Spot is a candidate only when existing Bookkeeping recovery, durable outputs and
idempotency withstand interruption. Include lost work, retries, startup and
capacity delay in the economics and deadline test; an advertised discount or
interruption warning is not a successful-run guarantee.
[Spot tradeoffs](https://docs.aws.amazon.com/batch/latest/userguide/bestpractice5.html).

Use task-level telemetry for standalone jobs. Compute Optimizer's documented
Fargate resource scope is ECS **services**; do not claim standalone pipeline task
recommendations from service support. Missing telemetry is a named gap, not a
reason to enable paid collection implicitly.
[Supported resources](https://docs.aws.amazon.com/compute-optimizer/latest/ug/supported-resources.html).

Return baseline versus candidate, correctness evidence, deadline result, total
cost and retry-adjusted assumptions. Obtain both expert reviews through the
production-support skill and applicable rollout approval. Current limits, price,
region/architecture availability and quotas must be verified for the selected
target before deployment; no benchmark or saving is implied by this guidance.
