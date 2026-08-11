# Assess cost/infrastructure-footprint implications of the new async architecture

Type: research
Status: resolved
Blocked by: (none)

## Question

[Research AWS messaging substrate options](02-research-messaging-substrate-options.md)
priced the messaging layer itself (S3/SNS/SQS/EventBridge — negligible,
under $2 for a full historical backfill). This ticket is different: it's
the *compute* footprint, not the messaging footprint.

Today's model is on-demand: Step Functions/ECS tasks run only while
`load_history`/`daily_incremental`/etc. execute, then stop — no idle
compute cost between runs. The new architecture's parallel-worker
consumers (draining the fan-out SQS queue) could be either:
(a) on-demand ECS tasks launched per SQS batch (via EventBridge Pipes'
ECS RunTask target, per ticket 02's research — task-per-message model,
no idle cost, but real launch latency and the documented "500 tasks/minute"
Fargate provisioning ceiling), or
(b) a long-running Fargate service continuously polling SQS (ticket 02's
other documented pattern — lower latency, scales via
`ApproximateNumberOfMessagesVisible`, but pays for idle capacity between
events unless scaled to zero).

Establish, with real figures (Fargate pricing, not estimates):

1. At this platform's real event volume (~625K accessions for a
   full-universe backfill; steady-state daily volume is far smaller,
   per ticket 02's own framing), what does each consumer model
   (task-per-message vs. long-running service) actually cost per month,
   for both the parallel-worker queue and the reducer queue?
2. Does a long-running reducer service (which needs to stay warm to merge
   deltas promptly, unlike the bursty parallel-worker fleet) change that
   calculus differently from the parallel-worker side?
3. Compare against today's on-demand-only cost baseline — is the new
   architecture's compute cost meaningfully higher, roughly flat, or
   lower (e.g. if today's `WindowedBootstrap` over-provisions task size
   for 14.5-hour sequential runs, per this session's own retry5
   observations, does finer-grained async work end up cheaper per unit of
   work done)?
4. Any other new fixed infrastructure cost from this architecture (e.g.
   the reducer's long-running service, if chosen, needs its own ECS
   service definition, load balancer or service-discovery if applicable,
   CloudWatch alarms) beyond what's already been priced.

## Answer

Method: pulled AWS Fargate's on-demand vCPU/memory rates directly from the
[AWS Price List API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/using-price-list-query-api.html)
(`https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonECS/current/us-east-1/index.json`,
same authoritative machine-readable source ticket 02 used for SNS/SQS, since
`aws.amazon.com/fargate/pricing/`'s own numbers cross-validate against it —
see below) and cross-checked against the directly-fetched
[`aws.amazon.com/fargate/pricing/`](https://aws.amazon.com/fargate/pricing/)
page. Verified the "500 tasks/minute" Fargate provisioning ceiling ticket 02
cited by re-fetching its source
([AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/process-events-asynchronously-with-amazon-api-gateway-amazon-sqs-and-aws-fargate.html))
directly — confirmed verbatim, still current. Checked ECS Service Auto
Scaling's own docs
([service-auto-scaling.html](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html))
for the scale-to-zero question rather than assuming an answer. Grounded task
sizing in this repo's own three ECS task profiles
(`infra/scripts/deploy-aws-application.sh:1158-1172`) rather than a generic
guess, and grounded the "new fixed infrastructure" question in a repo-wide
grep for `aws_ecs_service`/`aws_lb`/`aws_appautoscaling`/
`aws_cloudwatch_metric_alarm`/`aws_nat_gateway` across `infra/terraform/**`
— all return zero hits (checked below), which is itself the load-bearing
finding for Q4.

### 0. Grounding: this repo's real task sizes and Fargate's real rates

**Task profiles** (`infra/scripts/deploy-aws-application.sh:1158-1172`,
`register_task_definition <profile> <cpu> <memory>`):

| Profile | CPU units | Memory | vCPU / GB | Used today for |
|---|---|---|---|---|
| `small` | 512 | 1024 MB | 0.5 vCPU / 1 GB | `compute-windows`, `write-run-summary`, `mdm verify-graph` |
| `medium` | 1024 | 4096 MB | 1 vCPU / 4 GB | seed-universe, per-window `bootstrap-next`/fundamentals, most MDM steps |
| `large` | 2048 | 8192 MB | 2 vCPU / 8 GB | `gold-refresh`, `WindowedBootstrap`'s per-window step, `daily_incremental`'s `RunWarehouseTask` |

`large`'s 8192 MB ceiling (raised from 4096 on 2026-07-30, per CLAUDE.md's
"Gold-build memory" 5-whys) exists specifically because the *current*
architecture materializes an entire ~500-CIK window's silver/gold state in
one task's memory — a constraint this map's own isolated-producer design
(ticket 09) is built to eliminate for the new per-accession parallel
workers. Sizing the new architecture's consumers off `large` by default
would be importing the old architecture's memory profile into a shape that
no longer needs it — flagged explicitly since it changes the cost math
below by 4x if gotten wrong.

**Fargate on-demand rates, `us-east-1`** (AWS Price List API, confirmed
verbatim, SKUs `8CESGAFWKAJ98PME`/`PBZNQUSEXZUC34C9`):
- vCPU: **$0.0404800 per vCPU-hour**
- Memory: **$0.0044450 per GB-hour**
- Billing granularity, confirmed from the directly-fetched pricing page:
  per-second, **1-minute minimum** for Linux/X86 tasks.

**Public IPv4 surcharge, confirmed relevant to every task in this account**
(not a hypothetical add-on): grepped `infra/terraform/**` for
`aws_nat_gateway` — zero hits; `infra/terraform/modules/network_runtime/main.tf`
provisions only `aws_subnet "public"` (no private subnets, no NAT gateway);
every `RunTask` network configuration in `deploy-aws-application.sh`
hardcodes `"AssignPublicIp": "ENABLED"` (e.g. lines 1402, 1629, 1810, 2007,
2906, 3662). So every Fargate task this platform runs today — and any new
consumer task/service — holds a public IPv4 address for its running
duration. AWS's [VPC pricing page](https://aws.amazon.com/vpc/pricing/)
confirms: **$0.005 per hour per in-use public IPv4 address**, billed
whether the address is idle or active. This is a real, currently-paid cost
this platform already absorbs on every task; it's included below because it
compounds differently for the two consumer models (proportional to run time
for task-per-message, but a flat continuous charge for an always-on
service).

**Effective all-in hourly/per-minute cost per task profile** (compute +
public IP surcharge):

| Profile | $/hour | $/minute (1-min billing floor) |
|---|---|---|
| `small` (0.5vCPU/1GB) | $0.029685 | $0.00049475 |
| `medium` (1vCPU/4GB) | $0.06326 | $0.0010543 |
| `large` (2vCPU/8GB) | $0.12152 | $0.0020253 |

**When Fargate billing actually starts, re-checked rather than assumed**:
the same pricing page states billing runs "from the time you start to
download your container image until the Amazon ECS Task or Amazon EKS Pod
terminates" — **not** from when the container starts executing. For a
task-per-message consumer that launches a fresh task per batch, the billed
duration per launch is `max(1 minute, image-pull-time + run-time)`, not a
flat 1-minute floor. This repo has no direct measurement of its warehouse
image's cold-pull time on Fargate; a 30-90 second pull is a plausible range
for a Python/DuckDB/pyarrow/edgartools image, which would put a realistic
per-launch billed duration closer to 1-2.5 minutes than the bare 1-minute
floor. The tables below present both the floor-only figure (optimistic,
warm-cache case) and a 2.5x figure (conservative, ~150s billed per launch)
so the range is explicit rather than hidden in a single point estimate.

### 1. Cost per month, each consumer model, both queues, at real volume

**Verdict: at any batch size ≥10, both consumer models cost single digits to
low hundreds of dollars for the entire one-time 625K-accession backfill
(the range depends mainly on how much cold image-pull time compounds the
1-minute floor, not on task size), and well under a few dollars/day at any
plausible steady-state daily volume — but batch size 1 (literal
task-per-message) is genuinely expensive, dominated by Fargate's launch
overhead (billing floor plus image pull), not by real compute need.**

*Caveat on the 625K figure*: ticket 02 established ~625K as the count of
**bronze objects** in the prod bucket, not accessions; this ticket's own
framing (from the caller) asks the question in terms of accessions, and one
accession has multiple documents/objects, so the true accession count for a
full-universe backfill is lower than 625,000. Used as-is below per the
ticket's framing — it's a conservative upper bound on the real per-accession
event count, not an exact figure, so every dollar total below should be read
as "at most," not "exactly."

**Task-per-message (EventBridge Pipes → ECS RunTask), parallel-worker
queue, at 625,000 accession events (full backfill, one-time cost — this is
not a recurring monthly charge). Floor-only (optimistic) / 2.5x-floor
(conservative, cold-image-pull-inclusive) side by side:**

| Batch size | # task launches | `small` | `medium` | `large` |
|---|---|---|---|---|
| 1 (true one-event-per-task) | 625,000 | $309 / $773 | $659 / $1,647 | $1,266 / $3,164 |
| 10 | 62,500 | $31 / $77 | $66 / $165 | $127 / $316 |
| 100 | 6,250 | $3 / $8 | $7 / $16 | $13 / $32 |

At batch=1 the cost is driven almost entirely by task-launch overhead, not
real compute — **and batch=1 is independently ruled out by throughput, not
just cost**: at Fargate's documented 500-tasks/minute provisioning ceiling
(verified above), launching 625,000 individual tasks takes a minimum of
625,000 / 500 = **1,250 minutes (~20.8 hours)** of pure task-provisioning
time, before any actual work — comparable to or worse than today's 14.5-hour
`WindowedBootstrap` baseline (see §3). This independently reinforces
ticket 02's/ticket 04's already-locked design (per-accession events fed
through a Pipes config with a real batch size, not batch=1) on cost and
throughput grounds simultaneously, not just architectural ones.

**Reducer queue, task-per-batch (larger batch / multi-minute window, per
ticket 02's finding that the reducer needs its own differently-configured
queue) — priced at both volumes the question asks about, backfill and
steady state:**

- **During the 625K-event backfill**, the reducer fires on
  batch-size-reached, not the idle timer — at a 100-delta merge batch that's
  625,000/100 ≈ **6,250 reducer invocations concentrated in the backfill
  window**, the same order as the parallel-worker batch=100 row above:
  **$3-8 (`small`) / $7-16 (`medium`)** for the entire one-time backfill,
  floor-only/2.5x respectively.
- **At steady state**, the reducer's cadence is idle-timer-driven, not
  volume-driven — a trigger firing every 5 minutes even with nothing to
  merge (to keep latency bounded) is 288 invocations/day = 8,640/month,
  independent of daily accession count:

  | Profile | Monthly cost, floor-only | Monthly cost, 2.5x (cold-pull) |
  |---|---|---|
  | `small` | $4.28 | $10.70 |
  | `medium` | $9.11 | $22.78 |

**Long-running service (continuous SQS polling), either queue:** cost is
driven by *how busy* the fleet is, not by consumer model — for a fixed
amount of real work, running it on 1 worker for N hours or N workers for 1
hour costs the same total vCPU/GB-hours (ignoring per-worker overhead,
which Fargate doesn't meaningfully have once a task is running). The
distinguishing cost is **idle time**: a long-running service pays for every
hour it's up regardless of whether messages are waiting, unless scaled to
zero (§2). At the platform's real steady-state volume — no exact daily
accession count is documented anywhere in this repo as of this ticket (the
"Daily accession-expansion" 5-whys' 3,082-impacted-CIK/148,524-candidate
figures are a *pre-fix bug's* expansion, not a steady-state count, and the
post-fix RC run's real 7-day-window volume is explicitly still pending per
that same CLAUDE.md section) — cost is presented per 1,000 events instead so
it scales to whatever the true number turns out to be:

| Batch size | `small`, $/1,000 events | `large`, $/1,000 events |
|---|---|---|
| 10 | $0.0495 | $0.2025 |
| 100 | $0.00495 | $0.02025 |

Regardless of the undocumented exact daily count, steady-state parallel-worker
compute cost stays under $1/day for any daily volume up to tens of
thousands of events at any reasonable batch size — several orders of
magnitude below anything that would show up as a material line on this
platform's AWS bill.

### 2. Does the reducer's "stay warm" requirement change the calculus?

**Verdict: yes, but not in the direction the ticket's framing implies —
ECS Service Auto Scaling genuinely supports scaling to zero, which
undercuts the premise that "long-running" necessarily means "always pays
for idle capacity"; but if scaled to zero, it reintroduces the same
cold-start latency task-per-message has, defeating the reducer's actual
reason for wanting to stay warm. The always-on floor cost itself, when
quantified, is a real but small few-dollars-to-tens-of-dollars-a-month
number — and it is higher, not lower, than the periodic task-per-batch
alternative computed in §1.**

- **Scale-to-zero is real, confirmed from ECS's own docs, not assumed**:
  "If you want your task count to scale to zero when there's no work to be
  done, set a minimum capacity of 0." But the same paragraph continues:
  "when actual capacity is 0 and the metric indicates that there is
  workload demand, Service Auto Scaling waits for one data point to be sent
  before scaling out" — and ECS publishes metrics to CloudWatch on
  **1-minute intervals** (same doc). So a reducer service configured to
  scale to zero pays no idle cost, but reincurs (at minimum) a ~1-minute
  metric-detection delay plus normal task launch time before it can process
  a newly-arrived delta — structurally the same class of latency
  task-per-message already has, just moved from "per SQS batch" to "per
  cold period." **A reducer that scales to zero is not meaningfully
  different in latency character from task-per-message; it only stays
  meaningfully "warmer" if kept at `minCapacity ≥ 1`, in which case it pays
  the full floor cost below continuously.**
- **Always-on floor cost, smallest reasonable profile, 24/7 for a 30-day
  month (720 hours), using this repo's own `small`/`medium` profiles
  (§0's all-in rate including the public-IP surcharge, since a
  continuously-running service holds its public IP the whole time, not
  just during a brief task run):**

  | Profile | Monthly floor cost (720 hrs, `minCapacity=1`) |
  |---|---|
  | `small` (0.5vCPU/1GB) | **$21.37** |
  | `medium` (1vCPU/4GB) | **$45.55** |

  Compare this against §1's periodic task-per-batch reducer cost at
  steady-state idle cadence (`small`: $4.28-$10.70/month, `medium`:
  $9.11-$22.78/month depending on floor-only vs. cold-image-pull-inclusive
  billing) — **the always-on floor is ~2-5x more expensive in raw dollars
  than triggering a fresh task per accumulation window even under the more
  conservative pull-time assumption**, because most of those 720 hours/month
  the reducer has nothing to merge (this platform's real event rate, per
  §1, is nowhere close to saturating even a 5-minute cadence). This is the
  opposite of the intuition "a bursty producer can scale to zero, a reducer
  that needs to stay warm can't" — the reducer's actual choice is between a
  cheap periodic trigger (accepting up to ~5 minutes of latency, already
  implied by the batch-window design itself, independent of consumer model)
  or a costlier always-on floor that buys back only the marginal
  task-launch latency on top of that window, not the window itself.
- **Net for Q2: quantified, the "stay warm" premium is real (roughly
  $11-$35/month net of the periodic alternative, across the floor-only and
  cold-pull-inclusive estimates) but small in absolute terms — this should
  be a latency/operability decision, not a cost-avoidance one**, and the
  latency win it buys is smaller than the ticket's framing implies once
  scale-to-zero's own cold-start behavior is accounted for.

### 3. Comparison against today's on-demand baseline

**Verdict: today's baseline is already very cheap in absolute dollars
($1.76 for the entire `WindowedBootstrap` stage of a full-universe
backfill) — not because the current `large` task sizing is efficient, but
because Fargate bills for reserved capacity × wall-clock time, and the
total wall-clock time is what's bounded. The new architecture's compute
cost is roughly flat-to-higher in the worst case (small batch sizes) and
roughly flat-to-lower in the realistic case (batch ≥10, or a busy
long-running fleet) — it is not automatically cheaper just because the work
is more finely grained, and the "over-provisioned idle CPU" framing in the
ticket, while directionally real, isn't the dominant cost risk. The
dominant cost risk in the new architecture runs the other way: paying
Fargate's 1-minute billing floor on genuinely small units of work.**

- **Today's actual cost, computed, not estimated:** `WindowedBootstrap`'s
  53 sequential windows (`MaxConcurrency=1`) each launch their own `large`
  (2vCPU/8GB) task via Step Functions' Map state — this is 53 separate task
  launches totaling ~14.5 hours of aggregate `large`-task billed time, not
  one task continuously running for 14.5 hours (worth being precise about,
  since it changes nothing about the total bill: Fargate charges for total
  reserved-capacity-seconds consumed regardless of how many discrete task
  launches produced them, and 53 launches averaging ~16 minutes each are
  each far above the 1-minute billing floor, so the floor doesn't distort
  this number). 14.5 hours × $0.12152/hr (`large`, all-in with public IP)
  = **$1.76** for the entire Stage 1 backfill pass.
- **Is finer-grained work cheaper per unit of work done?** The ticket's own
  hypothesis — that the current `large` task pays for 8GB/2vCPU capacity
  most CIKs' I/O-bound work never uses — is directionally true (confirmed:
  `large`'s 8GB ceiling exists for OOM-avoidance during full-window silver
  materialization, per §0, not because 500 sequential CIKs' actual live
  working set needs 8GB continuously). But the dollar magnitude of that
  waste is tiny: even paying for the full 8GB/2vCPU for the full 14.5
  hours only costs $1.76. **There is very little idle-capacity waste left
  to recover in dollar terms** — the current baseline is not meaningfully
  overpaying today, because the total wall-clock duration itself, not the
  task size, dominates the bill, and 14.5 hours at any of this repo's three
  task sizes is under $4 regardless (`small`: $0.43, `medium`: $0.92,
  `large`: $1.76, all at 14.5 hrs).
- **Where the new architecture can lose money instead:** per §1, batch=1
  task-per-message at 625,000 events costs $309-$773 (`small`) up to
  $1,266-$3,164 (`large`) depending on task size and cold-image-pull
  assumption — **100x-1,800x more than today's $1.76** — from launch
  overhead (billing floor plus, per this revision, cold image-pull time)
  applied to units of work that individually take seconds. This is the real
  risk this comparison surfaces: finer granularity is cheaper only if the
  *task-launch granularity* (batch size) is kept coarser than the *event
  granularity* (per-accession, already locked by ticket 04) — conflating
  the two, i.e. genuinely one Fargate task per accession, is a real
  regression risk, not a hypothetical one.
- **This is not a like-for-like replacement of the $1.76 baseline — it's an
  addition on top of a cost that doesn't go away.** Today's $1.76 pays for
  bronze fetch *and* silver parse/write together, in one task
  (`map.md`'s "Current architecture baseline" note: they're genuinely
  coupled in the same process today, not just co-scheduled). Most of that
  14.5 hours of wall-clock is SEC-rate-limited fetch wait, not parse
  compute (per `map.md`'s own finding that intra-window artifact fetch is
  "already reasonably parallel" and the real ceiling is
  `WindowedBootstrap`'s window-level concurrency, not the rate limit
  itself). In the new architecture, bronze capture becomes its own
  independently-scaling process/task pool (this map's whole premise) and
  still pays for that same SEC-rate-limited wall-clock time — decoupling
  relocates that cost, it doesn't remove it, and this ticket doesn't
  re-price it (out of scope: it's the same fetch workload as today,
  no new consumer model to compare). So the honest comparison is: **new
  total ≈ (bronze capture, ~same order as today's fetch-bound cost) +
  (§1's parallel-worker parse/write cost, $31-$316 at batch=10) +
  (§1's reducer cost, $4-$23/month steady state)** — not §1's worker cost
  alone replacing the full $1.76. This doesn't change the verdict (every
  term in that sum is still single-to-low-triple-digit dollars, not a
  material re-architecture of the AWS bill), but it's the correct framing
  for anyone reading this ticket to size the *total* new-architecture
  compute spend, not just the newly-introduced consumer pieces.
- **At realistic batch sizes (≥10), the new architecture is roughly flat
  to modestly higher than today** ($31-$316 for batch=10 across the
  floor-only/cold-pull range and all three task sizes, vs. $1.76 today)
  **but for a materially different and better shape of work**: today's
  $1.76 buys one *sequential* 14.5-hour pass with a hard `MaxConcurrency=1`
  ceiling (the actual motivation for this whole map, per `map.md`'s
  "eliminate multi-day pipeline runtimes"); the new architecture's
  higher-but-still-trivial cost buys genuine parallelism bounded only by
  the 500-tasks/minute Fargate ceiling (§1) — a few hundred dollars a month
  at full-backfill scale, or cents a day at steady state, is not a
  meaningful tradeoff against removing an architectural throughput ceiling
  that this map exists specifically to remove. **Verdict: roughly flat in
  dollar terms at sane batch sizes, and the small delta that exists is not
  a reason to reconsider any locked decision** — it's a batch-size tuning
  parameter for ticket 12's implementation, not an architecture question.

### 4. Other new fixed infrastructure costs beyond ticket 02's messaging pricing

**Verdict: a task-per-message parallel-worker consumer adds no new fixed
infrastructure beyond what ticket 02 already covers (it reuses the existing
ECS cluster, task-definition, and public-subnet networking patterns
verbatim). A long-running reducer service, if chosen over task-per-batch,
would be genuinely new *infrastructure shape* for this repo — not just new
resource instances, but resource *types* this Terraform codebase has never
provisioned before — though the actual dollar cost of that new
infrastructure is near-zero; the real cost is operational surface, not
AWS spend.**

- **Confirmed via repo-wide grep, zero hits for all of:** `aws_ecs_service`,
  `aws_lb` (any ALB/NLB), `aws_service_discovery`, `aws_appautoscaling`,
  `aws_cloudwatch_metric_alarm`, `aws_cloudwatch_dashboard`, and
  `aws_nat_gateway` anywhere in `infra/terraform/**`. This repo's only ECS
  primitive today is one cluster (`aws_ecs_cluster.warehouse`,
  `infra/terraform/modules/warehouse_runtime/main.tf:94`) that Step
  Functions launches discrete `RunTask` invocations into — **there is no
  existing long-running ECS service anywhere in this repo to compare a new
  one against**; a reducer service would be a first-of-its-kind resource
  type for this Terraform codebase, not an incremental addition to an
  established pattern (unlike, say, a new SQS queue extending the
  already-proven SNS-fanout pattern per ticket 02).
- **What a new `aws_ecs_service` reducer would concretely require:**
  - `aws_ecs_service` itself (new resource type) — desired count, network
    configuration, deployment settings.
  - `aws_appautoscaling_target` + `aws_appautoscaling_policy` (new resource
    types) to scale on `ApproximateNumberOfMessagesVisible`, per ECS's own
    documented pattern (§0/§2) — likely a step-scaling policy sourced from
    a `aws_cloudwatch_metric_alarm` on that SQS metric (also a new resource
    type; zero exist in this repo today, even for the already-live
    `pipeline_notifications` failure-alert pipeline, which uses
    `aws_cloudwatch_event_rule` rule-matching, not metric alarms).
  - **No load balancer or service discovery needed** — a real, favorable
    finding, not assumed: this consumer only *pulls* from SQS, it accepts
    no inbound traffic, so the two heaviest pieces of a typical "add a
    long-running ECS service" checklist (ALB/target group, Cloud Map
    service discovery) simply don't apply here. This meaningfully narrows
    the gap between "new service" and "new task definition."
  - **Networking is reusable as-is**: the existing `network_runtime` module
    already provisions public subnets + `aws_security_group.ecs_public_tasks`
    (`infra/terraform/modules/network_runtime/main.tf:70`) that every
    `RunTask` invocation already uses — a new service can bind to the same
    subnets/security group, no new VPC resources required. (Confirms §0's
    finding that every task, new or old, pays the $0.005/hr public-IP
    surcharge — there's no NAT-gateway-backed private-subnet path in this
    account to avoid it, for either consumer model.)
  - A CloudWatch Logs group for the service (same pattern every existing
    task definition already uses — new instance of an existing type, not a
    new type).
  - An IAM task role/execution role (same pattern as every existing task
    role — new instance, not a new type).
- **Dollar cost of this new infrastructure itself is negligible**: no
  `aws_appautoscaling_*` or `aws_cloudwatch_metric_alarm` resource carries
  a direct charge at this platform's scale (CloudWatch alarm pricing is
  per-alarm-per-month, low single-digit dollars per alarm; Application
  Auto Scaling itself is free). **The actual new fixed cost this
  architecture introduces is the compute floor quantified in §2 (~$21-46/mo)
  if a long-running reducer is chosen with `minCapacity ≥ 1` — not the
  Terraform scaffolding around it.** If the reducer instead runs as
  task-per-batch (§1's recommendation), none of this new resource-type
  surface is needed at all — it reuses the identical `RunTask`/task-definition
  pattern every existing warehouse/MDM command already uses, making it the
  lower-new-infrastructure choice on this axis too, not just the
  lower-cost one.

## Verdict

1. **Both consumer models are cheap in absolute terms at this platform's
   real volume** — the one-time 625K-event backfill costs roughly $3-$32 at
   the most efficient realistic batch size (100) and $31-$316 at a more
   conservative batch size (10), across all three task sizes and both the
   floor-only and cold-image-pull-inclusive billing estimates; steady-state
   daily cost stays under a few dollars/day regardless of the undocumented
   exact daily volume. **Batch size 1 (true task-per-message) is the one
   configuration that is genuinely expensive** ($309-$3,164 for the
   backfill depending on task size and pull-time assumption), driven by
   Fargate's launch overhead (1-minute billing floor, likely compounded by
   cold container-image-pull time — billing starts at image download, not
   task start, per AWS's own pricing page) on sub-minute units of work — and
   it's independently ruled out by the 500-tasks/minute Fargate
   provisioning ceiling before cost even enters the picture (~20.8 hours
   just to launch 625,000 tasks). This reinforces, on a third independent
   axis (cost + throughput, on top of ticket 02's architectural reasoning),
   the already-locked per-accession-event-with-real-batching design.
2. **ECS Service Auto Scaling genuinely supports scaling to zero** (`docs`
   quote: "set a minimum capacity of 0") — contradicting the ticket's own
   framing that a long-running reducer necessarily pays idle-capacity cost.
   But scaling to zero reintroduces the same class of cold-start latency
   task-per-message already has (≥1-minute CloudWatch metric interval plus
   task launch time), undercutting the reducer's actual reason for wanting
   to be "long-running" in the first place. Quantified always-on floor cost
   (`minCapacity=1`, `small`/`medium`, 24/7/month): **$21.37 / $45.55** —
   real money, but **~2-5x more expensive than the periodic task-per-batch
   alternative** ($4.28-$10.70 / $9.11-$22.78/month, floor-only to
   cold-pull-inclusive) computed for the same reducer role, even after the
   more conservative image-pull assumption is applied to both sides.
3. **Today's on-demand baseline is already cheap** ($1.76 for the entire
   14.5-hour `WindowedBootstrap` stage, fetch and parse/write combined)
   because Fargate bills reserved-capacity × wall-clock-time and the total
   wall-clock time is what's bounded — there isn't much idle-capacity waste
   left to recover in dollar terms, even though the "oversized task for
   I/O-bound work" critique is directionally correct. The new architecture's
   **newly-introduced parse/write consumer pieces** are roughly flat to
   modestly higher than today at sane batch sizes (~$31-$316 for the full
   backfill at batch=10, vs. today's $1.76) — but that $1.76 already bundles
   fetch, which the new architecture relocates (not eliminates) into its own
   separately-scaled bronze-capture tasks not re-priced by this ticket, so
   the honest new-architecture total is bronze-capture-cost (≈ today's,
   unchanged) plus the new consumer pieces, not the new pieces alone
   replacing $1.76. Either way, the real payoff of the new architecture is
   removing the `MaxConcurrency=1` throughput ceiling (this map's actual
   motivation), not compute-dollar savings, and that payoff is not
   threatened by this small a cost delta.
4. **No new fixed AWS-service cost of consequence beyond §2's already-priced
   floor** — but a long-running reducer service would be a genuinely new
   *resource-type* surface for this repo's Terraform (first `aws_ecs_service`,
   `aws_appautoscaling_*`, `aws_cloudwatch_metric_alarm` ever, confirmed via
   zero existing hits), even though it needs no load balancer or service
   discovery (pull-only consumer) and can reuse existing cluster/networking.
   A task-per-batch reducer needs none of this new surface at all.

**Hardened to a locked constraint (2026-08-11, user directive): on-demand
only, never always-on, cheapest viable option — not merely a
recommendation subject to revisiting.** This settles the one thing this
ticket had left open to judgment (task-per-batch vs. a warm always-on
reducer, §2's 2-5x cost gap) in favor of on-demand unconditionally, and
additionally elevates Fargate Spot from a footnote to a locked choice for
the parallel-worker queue: SQS redelivery already makes each worker
interrupt-tolerant by construction (an interrupted Spot task's message
simply becomes visible again for another worker to pick up), so Spot's
up-to-70%-off pricing is close to free money here, not a reliability
trade-off — a further ~2-4x reduction on top of the already-cheap
task-per-batch figures in §1. Not applied to the reducer queue: it's
lower-volume, and interruption mid-merge is exactly the failure mode
ticket 13 needs to design retry semantics around deliberately, not
introduce speculatively via Spot before that design exists.

**Recommendation:** default **task-per-message (EventBridge Pipes → ECS
RunTask), batched — not literally per-message** for **both** queues:
- **Parallel-worker queue**: small-to-moderate batch size (≥10, tuned
  against the real per-accession parse duration once measured — this
  ticket found no existing measurement of that duration in this repo),
  sized on the `small` profile (0.5vCPU/1GB) as the starting point, not
  `large` — `large`'s memory ceiling exists for a full-window
  materialization problem the new isolated-producer design (ticket 09)
  specifically removes; carry `medium` as the fallback if real
  per-accession memory use proves larger than expected, the same
  escalation pattern this repo's own OOM history (§0's "Gold-build memory"
  citation) already establishes as its go-to fix.
- **Reducer queue**: also task-per-batch (larger batch size / multi-minute
  window, per ticket 02's design), not a long-running always-on service —
  it is measurably cheaper (~2-5x) than an always-on `minCapacity=1` service
  for the same role, needs none of §4's new Terraform resource types, and
  the latency it "gives up" relative to an always-on service is smaller
  than it first appears once ECS's own scale-to-zero cold-start behavior is
  accounted for. Revisit only if a real production run shows the reducer
  queue's actual invocation rate is high enough that per-invocation
  overhead (not idle time) starts to dominate — nothing in this platform's
  known event volume (§1) suggests that today.
- **Worth folding into ticket 13's design, not costed above but cheap to
  add**: the parallel-worker fleet is a natural fit for
  [Fargate Spot](https://aws.amazon.com/fargate/pricing/) (up to 70% off
  on-demand, per the same pricing page fetched in §0) specifically because
  SQS redelivery already makes each worker interrupt-tolerant by
  construction — an interrupted Spot task's message simply becomes visible
  again and gets retried by another worker, which is exactly the semantics
  ticket 13 needs to design regardless of interruption source. This gives
  ticket 13's idempotency/retry finding a direct cost payoff (a further
  ~2-4x reduction on top of §1's parallel-worker figures) rather than being
  purely a reliability concern — not recommended for the reducer, which is
  lower-volume and where interruption mid-merge is exactly the failure mode
  ticket 13 should be most careful about.

**For tickets 12/13:** this ticket's cost delta from today's baseline is
small enough (roughly $30-$320/month at full-backfill batch=10 sizing
depending on task size and pull-time assumption, a few dollars/day or less
at steady state) that **ticket 12's migration sequencing should not be gated
or reshaped by cost** — a phased rollout, a big-bang cutover, and a
parallel-run/shadow approach are all affordable under this cost model, so
ticket 12 should decide sequencing purely on operational-risk grounds (its
own framing), not cost. **Ticket 13 should weight retry/DLQ policy toward
the throughput finding in §1, not the cost finding**: because batch=1 is
already ruled out on throughput grounds independent of cost, ticket 13's
retry semantics need to account for **redelivery of a whole batch, not a
single accession**, when a batched parallel-worker task fails partway
through — a batch-level retry/DLQ design (not a per-message one) is the
correct frame given the batch sizes this ticket's cost/throughput analysis
recommends, and that's a design input ticket 13 doesn't yet have.
