# Research AWS messaging substrate options for bronze-write fan-out

Type: research
Status: resolved
Blocked by: (none)

**Framing corrections (2026-08-11), read before researching:**
- Question 2b's premise ("this map's destination explicitly includes
  unifying/rethinking the dual gold path") is stale. [Decide the fate of
  the dual gold path](05-decide-dual-gold-path-fate.md) found there is no
  dual compute path — gold has one compute engine (Python). Snowpipe
  Streaming is still worth researching, but frame it as input to [Decide
  whether gold compute stays in Python/DuckDB or moves into Snowflake
  SQL](08-decide-gold-compute-location.md), not as "unifying" anything.
- [Decide silver's write/storage target](09-decide-silver-write-storage-target.md)
  already decided silver stays on DuckDB, via an isolated-producer +
  single-reducer pattern generalized to fire per-event (multiple async
  parse workers write independent immutable deltas; one reducer merges
  them). The same per-event-reducer shape was independently reached for
  MDM's entity export ([ticket 06](06-decide-mdm-role-in-new-architecture.md))
  and graph sync ([ticket 10](10-decide-graph-sync-role-in-new-architecture.md)).
  Factor this into question 2's consumer model: the substrate needs to
  support both "fan out to N parallel workers" AND "trigger a single
  reducer once/whenever relevant deltas exist," which may be two different
  consumption patterns on the same queue rather than one.

## Question

This map's destination requires bronze capture to emit an event on write
that both an independent silver consumer AND an independent gold consumer
react to — a fan-out, not a single point-to-point handoff. This repo
already has one working precedent to build from: the Snowflake export leg
(S3 export Parquet bucket -> S3 event notification -> SNS topic ->
`SNOWFLAKE_RUN_MANIFEST_TASK` picks up the manifest and refreshes
`EDGARTOOLS_GOLD` within ~1 minute) — confirmed live in this session's own
deploy output (`S3 -> SNS notification configured on
edgartools-prod-snowflake-export-... for manifest prefix`).

Research, with citations from AWS's own documentation/pricing pages (not
general knowledge):

1. **Fan-out shape**: for "one bronze-write event, multiple independent
   consumers" — compare S3 Event Notifications -> SNS -> multiple SQS
   subscriptions (extends the existing precedent) vs. EventBridge (built
   for multi-consumer event routing, rule-based filtering) vs. Kinesis Data
   Streams (ordered, replayable, but heavier operational model). Which is
   the natural extension of what's already deployed vs. a genuinely new
   piece of infrastructure?
2. **Consumer model**: for consumers that need to run a real ECS
   Fargate task (silver parse needs DuckDB, meaningful CPU/memory) rather
   than a lightweight Lambda — does SQS-triggered ECS (via EventBridge Pipes
   or a polling worker) fit better than Lambda-based consumption? What are
   the concrete integration patterns AWS documents for "SQS queue drains
   into long-running Fargate tasks"?
2b. Snowflake's own **Snowpipe Streaming** API is a possible alternative for
   the *gold-via-Snowflake* leg specifically (bypassing S3 native pull
   entirely for lower latency) — is this worth comparing against the
   existing S3-event-notification-driven native pull, given this map's
   destination explicitly includes unifying/rethinking the dual gold path?
3. **Cost model**: rough per-event/per-message pricing for each option at
   this platform's actual bronze-write volume (this session separately
   established ~625K bronze objects, ~72GB, in the `edgartools-prod-bronze`
   bucket as of 2026-08-06 — cite AWS's current pricing pages, don't
   estimate from memory).
4. **Existing constraint check**: CLAUDE.md's "Image management" section
   states "Use AWS ECR only for deployable images... unless the platform
   architecture changes explicitly" — this map IS an explicit platform
   architecture change, but confirm there's no other standing constraint in
   this repo (Terraform modules, IAM boundary docs) that would rule out a
   candidate substrate before it's even compared on merits.

## Answer

Method: read this repo's actual live messaging wiring end to end — the
Snowpipe auto-ingest precedent
(`infra/terraform/snowflake/modules/native_pull/main.tf:660-667`,
`infra/terraform/modules/warehouse_runtime/main.tf:72-75`,
`infra/terraform/access/aws/modules/runtime_access/main.tf:30-68`,
`infra/scripts/deploy-aws-application.sh:797-816`) and the separate,
already-deployed EventBridge-to-SNS failure-alert pipeline
(`infra/terraform/modules/pipeline_notifications/main.tf:15,96,132`,
`infra/terraform/access/aws/modules/runtime_access/main.tf:313-359`) — then
grepped all of `infra/terraform/**` for `aws_sqs_queue`/`aws_kinesis_stream`
(zero hits, confirmed below) and `CONTEXT.md`/`docs/adr/*` for any standing
IAM/region/service constraint. Cross-referenced against AWS's own official
docs and pricing pages (fetched directly, cited by URL below). Where a
consumer-facing pricing page's numeric tables were JS-rendered and not
extractable as plain text by the fetch tool (SNS, SQS, S3), went directly to
AWS's authoritative machine-readable source instead of relying on secondary
corroboration: the [AWS Price List
API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/using-price-list-query-api.html)'s
public, unauthenticated `us-east-1` price list endpoints
(`https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<ServiceCode>/current/...`)
for `AmazonSNS`, `AWSQueueService` (SQS), and `AmazonS3`, `curl`'d and
parsed directly — this is AWS's own pricing data, the same source
`aws.amazon.com/*/pricing/` renders from client-side, not a third-party
estimate.

### 0. The existing precedent, precisely (not just as described in the ticket)

The ticket's own framing ("S3 export Parquet bucket -> S3 event notification
-> SNS topic -> `SNOWFLAKE_RUN_MANIFEST_TASK`") is confirmed accurate, and
the actual wiring is worth being precise about because it changes the
"natural extension" argument in §1:

- The S3 bucket notification itself is **not** a Terraform resource — it's
  set out-of-band by `aws s3api put-bucket-notification-configuration` in
  `deploy-aws-application.sh:797-816`, filtered to
  `suffix: "run_manifest.json"`, targeting one SNS topic ARN.
  `TopicConfigurations` is a list, so this mechanism already supports
  multiple, independently prefix/suffix-filtered topic targets on the same
  bucket without new infrastructure — relevant to ticket 04's granularity
  question, since different event granularities could route to different
  topics from the same bucket today.
- The SNS topic (`aws_sns_topic.snowflake_manifest_events`,
  `warehouse_runtime/main.tf:72-75`) and its resource policy
  (`runtime_access/main.tf:30-68`) are genuinely Terraform-managed.
- **Today this topic has exactly one subscriber: Snowflake's own
  Snowpipe-managed SQS queue**, via `snowflake_pipe.manifest`'s
  `auto_ingest = true` / `aws_sns_topic_arn` (`native_pull/main.tf:660-667`).
  Snowflake creates and owns that queue; this repo never provisions an SQS
  resource for it. So the literal precedent is "S3 -> SNS -> exactly one
  subscriber," not yet a demonstrated multi-subscriber fan-out — extending it
  to N subscribers means adding N new SQS subscriptions to an
  already-Terraform-managed topic, which is additive, not a rebuild.
- **EventBridge is already live in this account**, independently of
  anything gold- or bronze-related: `pipeline_notifications` module
  (`aws_cloudwatch_event_rule.pipeline_failures` at
  `pipeline_notifications/main.tf:96`, catching all
  `edgartools-{env}-*` Step Functions `FAILED` executions, targeting the
  same-module SNS topic via `aws_cloudwatch_event_target` at `main.tf:132`)
  and `daily_incremental`'s EventBridge schedule (referenced in
  `docs/runbook.md:417` and `docs/release-readiness/go-live-status-2026-07-23.md`).
  The Step Functions IAM role already has `events:PutTargets`/`PutRule`/
  `DescribeRule` (`runtime_access/main.tf:313,355-359`). So "EventBridge" as
  a technology is not new operational ground for this AWS account — only
  *using it for data-object fan-out routing* (as opposed to its current job,
  routing AWS-service state-change events) would be new.
- **Confirmed zero `aws_sqs_queue` or `aws_kinesis_stream` resources exist
  anywhere in `infra/terraform/**`** (`grep -rn "aws_sqs_queue\|aws_kinesis_stream"
  infra/terraform --include="*.tf"` — no output). Both are genuinely
  net-new resource types for this repo's Terraform, though (per §1/§4) that
  matters much more for Kinesis than for SQS.

### 1. Fan-out shape: S3->SNS->SQS vs. EventBridge vs. Kinesis Data Streams

**Verdict: S3 Event Notifications -> SNS -> multiple SQS subscriptions is
the natural extension; EventBridge is a real, already-operated alternative,
not "genuinely new infrastructure," but it would be new *for this specific
job*; Kinesis is the only one of the three that is genuinely new
infrastructure to operate end to end.**

- AWS's own [S3 Event Notifications overview](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html)
  confirms all four candidate destinations — SNS, SQS, Lambda, and
  EventBridge — are natively supported directly from an S3 bucket
  notification configuration, so the choice isn't "does S3 support X," it's
  which fan-out shape sits on top.
- AWS's own [SNS-to-SQS fanout doc](https://docs.aws.amazon.com/sns/latest/dg/sns-sqs-as-subscriber.html)
  describes exactly this repo's shape as the canonical pattern: "When you
  subscribe an Amazon SQS queue to an Amazon SNS topic, you can publish a
  message to the topic and Amazon SNS sends an Amazon SQS message to the
  subscribed queue" — i.e. adding a second (third, fourth...) SQS
  subscription to the existing `snowflake_manifest_events`-shaped topic
  pattern is exactly the documented mechanism, using a resource type
  (`aws_sns_topic_subscription`) this repo already has one working example
  of provisioning correctly (the pipeline-failures email subscription,
  `pipeline_notifications/main.tf` "SNS Email Subscription" block).
- AWS's own [SQS-vs-SNS-vs-EventBridge decision guide](https://docs.aws.amazon.com/decision-guides/latest/sns-or-sqs-or-eventbridge/sns-or-sqs-or-eventbridge.html)
  (dated November 2025, so current) states SNS's typical use case as
  "Fanout notifications, pub/sub messaging" while EventBridge's is
  "event-driven architectures, real-time stream processing, cross-account
  event sharing" — and gives the concrete differentiator relevant here:
  EventBridge supports "complex event pattern matching and content-based
  filtering," where SNS offers only "subscription filter policies based on
  message metadata." If this map's consumers need to route on event
  *content* (e.g. "route to the ownership-parse queue only if form type is
  3/4/5"), EventBridge's rule engine is the documented tool for that; SNS's
  filter policies can still do attribute-based routing (already used
  implicitly by this repo's SNS topic filtering-by-suffix at the S3 layer)
  but are coarser.
- **Kinesis Data Streams is qualitatively different and not a drop-in
  fan-out substrate at all** — it has no native S3 event notification
  destination (S3 can target SNS/SQS/Lambda/EventBridge only, per the same
  overview doc above; getting S3 events into Kinesis requires an
  intermediate hop, e.g. EventBridge -> Kinesis or a Lambda producer). Its
  actual value proposition (ordering, replay via a configurable retention
  window, multiple independent consumers via enhanced fan-out) is real but
  answers a different question than "fan out one bronze-write event to N
  consumers" — it's for consumers that need to *replay* a stream of history,
  not just react to a live event. Nothing in this map's destination (bronze
  capture, silver parse, gold refresh) requires replaying an ordered
  historical event log; every layer above bronze already reads its input
  from a durable object store (S3), not from the event stream itself, so
  Kinesis's core differentiator is unused here. Confirmed no existing
  Kinesis footprint anywhere in the repo's Terraform (§0).
- **Net:** SNS is the "natural extension" in the strict sense the ticket
  asks about — same resource types, same account, same working pattern,
  additive change. EventBridge is a legitimate technical alternative
  already running in this account (so "new infrastructure to operate" is
  not really true of it — the ops burden of EventBridge itself is already
  paid for) but would be a new *usage* of it (event-driven data routing
  vs. today's AWS-service-state-change routing) and its content-based
  filtering is the one capability SNS can't cleanly match if ticket 04 ends
  up wanting to fan out differently per form type. Kinesis is the only
  candidate that is genuinely new operational surface top to bottom
  (stream provisioning, shard/on-demand capacity decisions, IAM roles,
  monitoring) for a capability (ordered replay) this map's design doesn't
  need.

### 2. Consumer model: SQS-triggered ECS Fargate, and the dual fan-out/reducer requirement

**Verdict: SQS-triggered ECS via EventBridge Pipes is a real, directly
AWS-documented pattern (not something bolted together from unrelated
primitives), and the same SQS+Pipes substrate can be configured two
different ways to serve both consumption shapes this map needs — but not
from a single shared queue; it needs two independently-configured queues
(or pipes) fed by the same SNS fan-out, one shape per queue.**

- **SQS -> ECS Fargate is directly documented**, two ways:
  - **EventBridge Pipes with an ECS task target.** AWS's own
    [EventBridge Pipes targets doc](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-event-target.html)
    lists "ECS task" as a first-class supported target type — "All Amazon
    ECS `runTask` parameters are configured explicitly through
    `EcsParameters`" — alongside SQS as a first-class
    [supported source](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-event-source.html).
    AWS Serverless Land also publishes a named, deployable pattern for
    exactly this: "Trigger ECS task from Amazon SQS using Amazon
    EventBridge" (`serverlessland.com/patterns/eventbridge-sqs-ecs-cdk`).
    This is a managed, no-glue-code integration — no Lambda shim needed to
    bridge SQS to `ecs:RunTask`.
  - **A long-running Fargate service that polls SQS itself.** AWS
    Prescriptive Guidance's ["Process events asynchronously with API
    Gateway, SQS, and AWS Fargate"](https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/process-events-asynchronously-with-amazon-api-gateway-amazon-sqs-and-aws-fargate.html)
    documents step 5 of its architecture as "Fargate pulls the message from
    the SQS queue, processes the event" — a continuously-running ECS
    service (not a task-per-message model) doing its own SDK-level
    long-polling, the shape a merge/reduce worker would actually want.
    ECS's own [Service Auto Scaling
    docs](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html)
    document target-tracking scaling on custom CloudWatch metrics, which is
    how such a service would typically be scaled against
    `ApproximateNumberOfMessagesVisible`.
  - Both patterns are AWS-documented, not "genuinely new" glue; the choice
    between them is really "one Fargate task per SQS batch" (Pipes) vs. "one
    long-lived Fargate service draining continuously" (polling worker), not
    a documented-vs-improvised distinction.
- **Does one substrate cleanly support both "fan out to N parallel workers"
  and "trigger one reducer once deltas have accumulated"?** The evidence
  says: **yes, the same primitive (SQS, optionally via EventBridge Pipes)
  can be configured either way — but the two shapes need their own queue,
  not one shared queue used two ways.** This matters directly for tickets
  06/09/10's "generalize a one-shot reducer to fire per-event" design:
  - AWS's [SQS-as-EventBridge-Pipes-source doc](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-pipes-sqs.html)
    documents exactly the parameters that produce each shape from the same
    mechanism: "By default, EventBridge polls up to 10 messages... To avoid
    invoking the pipe with a small number of records, you can tell the
    event source to buffer records for up to five minutes by configuring a
    batch window. Before invoking the pipe, EventBridge continues to poll
    messages... until one of these things occurs: the batch window
    expires... the configured maximum batch size is reached." This is,
    verbatim, an AWS-managed "N deltas or timer, whichever first" trigger —
    exactly the shape ticket 09's reducer needs, with no custom scheduling
    logic to write.
  - The same doc's scaling section documents the fan-out shape too: "When
    messages are available, EventBridge reads up to five batches and sends
    them to your pipe. If messages are still available, EventBridge
    increases the number of processes that are reading batches by up to
    300 more instances per minute. The maximum number of batches that a
    pipe can process simultaneously is 1,000" — i.e. a pipe configured with
    a small batch size (down to 1) and no batch window scales out
    aggressively and in parallel, giving the N-parallel-worker shape from
    the identical mechanism. (Real-world ceiling worth noting alongside
    this: AWS Prescriptive Guidance's Fargate-polling pattern above states
    "Concurrent jobs are limited to 500 tasks per minute, which is the
    maximum number of tasks that Fargate can provision" — a hard platform
    ceiling on how fast N-parallel-worker fan-out can ramp, independent of
    which messaging substrate feeds it.)
  - **The catch, and why this is "two configurations of one substrate," not
    "one queue, two behaviors":** an SQS message is a competing-consumers
    primitive — once one consumer (or one pipe) receives and deletes it,
    no other consumer sees it. A single queue cannot simultaneously feed
    "one message triggers one independent parse worker" and "accumulate
    many messages, then trigger one reducer" — those are mutually exclusive
    readings of the same message. The architecturally correct shape,
    consistent with SNS's fan-out role from §1, is: SNS publishes once per
    bronze-write event, fanning out to **two SQS queues** — one drained by
    an N-parallel-worker pipe/config (batch size near 1, no window) for
    independent parse workers, the other drained by a reducer pipe/config
    (larger batch size, multi-minute window) or a long-running polling
    Fargate service for the merge step. Both queues are the same substrate
    (SQS, fed by the same SNS topic), configured differently — not two
    different technologies bolted together, but not literally one queue
    serving both roles either. This directly informs ticket 04/09's design:
    the "one-shot reducer generalized to fire per-event" pattern maps
    cleanly onto a *second*, differently-configured SQS consumer off the
    same fan-out topic, not onto the same queue the parallel parse workers
    drain.

### 2b. Snowpipe Streaming as an alternative to today's S3-native-pull for gold

**Verdict: not worth switching to for the gold-into-Snowflake leg as it
exists today — the latency win is real but modest relative to this
pipeline's own runtime, the cost gap AWS/Snowflake had between the two
paths was closed platform-wide in December 2025, and adopting it requires
replacing the write path, not extending it.** Framed, per the correction in
this ticket's header, as input to
[ticket 08](08-decide-gold-compute-location.md), not as resolving any "dual
path" question — there is no dual path to unify (ticket 05).

- **What it requires:** Snowflake's own [Snowpipe Streaming
  overview](https://docs.snowflake.com/en/user-guide/data-load-snowpipe-streaming-overview)
  states it "ingests rows directly... bypassing the need for staging files
  or intermediate cloud storage," via a Python SDK (Python 3.9+, confirmed
  current and actively maintained — the [SDK's 2026 release
  notes](https://docs.snowflake.com/en/release-notes/clients-drivers/snowpipe-streaming-sdk-2026)
  show a release as recently as 2026-07-23). This is a **materially
  different write path** from what this repo has today
  (`write_gold_table_to_serving_export` writing Parquet to S3, consumed by
  `GOLD_EXPORT_MAP`/the native-pull `COPY INTO` — CLAUDE.md's own
  architecture diagram). Adopting Streaming means the warehouse's gold-write
  code would call the Snowflake SDK directly per row/batch instead of
  writing an S3 export artifact at all — not an additive change to the
  existing manifest/native-pull mechanism, a parallel one that would need
  its own operational hardening (offset-token tracking for exactly-once
  delivery, channel management) that the current file-based path doesn't
  need.
- **Latency:** Snowflake states Streaming achieves "as low as 5 seconds"
  ingest-to-query latency, vs. this repo's own confirmed ~1-minute
  `SNOWFLAKE_RUN_MANIFEST_TASK` cadence (CLAUDE.md, and independently this
  ticket's own §0 tracing of the live S3->SNS->Snowpipe wiring). A ~55-second
  latency win is real but small next to the multi-minute-to-multi-hour
  runtimes this whole map exists to shrink (see the map's own "eliminate
  multi-day pipeline runtimes" motivation) — gold refresh today is gated on
  the full upstream chain completing, not on this specific hop's latency.
- **Cost:** as of [Snowflake's Dec 8, 2025 pricing simplification release
  note](https://docs.snowflake.com/en/release-notes/2025/other/2025-12-08-snowpipe-simplified-pricing),
  file-based Snowpipe moved to the same flat **0.0037 credits per GB
  ingested** model that Snowpipe Streaming's [high-performance-architecture
  cost doc](https://docs.snowflake.com/en/user-guide/snowpipe-streaming/snowpipe-streaming-high-performance-cost)
  also documents — the release note explicitly frames this as replacing
  "the former cost model['s]... per-second/per-core... and... per-1,000-files
  charge," i.e. **the cost gap that historically favored file-based
  Snowpipe for large batches is gone**; this repo's existing native-pull
  path is not cheaper than Streaming on a per-GB basis today. Cost is
  therefore not a reason to switch, but it's also not a reason not to —
  it's a wash.
- **Net:** worth keeping on the table as a future option for whichever gold
  compute location ticket 08 lands on (if gold compute ever moves closer to
  Snowflake-native, row-level streaming would fit that shape better than
  today's batch-Parquet-export shape does), but not a change this ticket
  recommends making to the *existing* Python/DuckDB gold-export path on its
  own merits.

### 3. Cost model at this platform's actual bronze-write volume (~625K objects, ~72GB)

**Verdict: at this platform's real volume, S3 Event Notifications, SNS,
SQS, and EventBridge are all cost-negligible (low single-digit dollars for
a one-time 625K-event backfill, and steady-state daily volume is far
smaller than that) — cost does not meaningfully differentiate among them at
any plausible event granularity ticket 04 might choose. Kinesis Data
Streams is the one option with a real, volume-independent fixed cost.**
Figures below are drawn directly from AWS's own Price List API (pulled live
against `us-east-1`, see Method) for S3, SNS, and SQS, and from the
directly-fetched consumer pricing pages for EventBridge and Kinesis (whose
tables rendered as extractable text). No figure in this section is from a
third-party blog.

- **S3 requests** (AWS Price List API,
  `AmazonS3`/`us-east-1`, SKU group `S3-API-Tier1`): confirmed verbatim —
  `"$0.005 per 1,000 PUT, COPY, POST, or LIST requests"`
  (`pricePerUnit.USD = 0.000005`). This charge is already being paid today
  for every bronze write regardless of whether a notification is attached.
  AWS's own [S3 Event Notifications
  doc](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html)
  plus the S3 pricing page's own text (directly fetched) confirm there is
  **no separate charge for the notification itself** — "there is no charge
  for the S3 Event Notifications feature itself. You will pay the usual
  messaging and execution charges for SQS, SNS, and Lambda."
- **SNS** (AWS Price List API, `AmazonSNS`/`us-east-1`): confirmed
  verbatim — Publish requests, SKU group `SNS-Requests-Tier1`:
  `"$0.50 per 1,000,000 Amazon SNS API Requests per month thereafter"`
  (`pricePerUnit.USD = 0.0000005`). Delivery specifically to SQS, SKU
  `DeliveryAttempts-SQS`: `"There is no charge for SQS Notifications"`
  (`pricePerUnit.USD = 0`) — confirming SNS bills **only** the Publish call
  to the topic, not per-subscriber delivery, so fanning one publish out to
  **two** SQS queues (per §2's design) does not double this cost: it stays
  at 625,000 Publish requests regardless of subscriber count. Against the
  documented 1,000,000-requests/month free tier (from the directly-fetched
  `aws.amazon.com/sns/pricing/` page text; the free-tier *threshold* itself
  rendered as plain text even though the priced-tier dollar table didn't),
  625,000 monthly publishes either land entirely inside that free tier or,
  worst case if other usage in this shared account already consumes it,
  cost 625,000 × $0.50/million ≈ **$0.31**. One caveat stated plainly rather
  than glossed over: the free tier is account-wide and monthly, not
  reserved for this pipeline, so "inside the free tier" isn't guaranteed if
  concurrent SNS usage elsewhere in the account is high that month — but
  even the non-free-tier price is negligible.
- **SQS** (AWS Price List API, `AWSQueueService`/`us-east-1`, SKU group
  `SQS-APIRequest-Tier1`, tiered by `beginRange`/`endRange`): confirmed
  verbatim — `"$0.40 per million Amazon SQS standard requests in Tier1"`
  for the 0–100,000,000,000-request/month band (`pricePerUnit.USD =
  0.0000004`), stepping down to $0.30/million (100B–200B) and $0.24/million
  (200B+) — far outside this platform's volume, included only for
  completeness. The directly-fetched `aws.amazon.com/sqs/pricing/` page
  text separately confirms the free tier: "All customers can make 1 million
  Amazon SQS requests for free each month," and that a message consumes
  multiple requests (send + receive + delete, minimum 3 per
  message-lifecycle; "each 64 KB chunk of a payload is billed as 1
  request"). Per §2's finding that the fan-out/reducer duality needs **two**
  independently-drained SQS queues off one SNS topic (unlike SNS's
  publish-side cost, per-queue SQS request cost **does** multiply with
  subscriber count, since each queue independently receives, and its own
  consumer independently receives+deletes, every message): 625,000 events ×
  2 queues × ~3 requests/message ≈ 3.75M requests, minus the shared
  1M/month free tier ≈ 2.75M billable × $0.40/million ≈ **$1.10** for a full
  625K-object backfill. Negligible at this platform's scale either way.
- **[EventBridge](https://aws.amazon.com/eventbridge/pricing/):** confirmed
  directly from the fetched page: custom event bus ingestion is $1.00 per
  million events published, same-account delivery to a target is $0.00/million
  (free), and EventBridge Pipes processing is $0.40 per million requests
  (64KB payload chunks). At 625,000 events: ingestion ≈ **$0.63**, Pipes
  processing ≈ **$0.25** — under $1 total for the same full backfill volume,
  comparable to the SNS+SQS path.
- **[Kinesis Data Streams](https://aws.amazon.com/kinesis/data-streams/pricing/):**
  confirmed directly from the fetched page (US East): on-demand mode is
  $0.08/GB data-in, $0.04/GB data-out, **plus $0.04/hour per stream
  regardless of traffic** (provisioned mode: $0.015/shard-hour +
  $0.014/million PUT payload units, same shape — a per-shard-hour floor
  that accrues whether or not bronze is being written). For event-sized
  messages (not the 72GB of bronze *content* itself — nothing in this map's
  design puts raw bronze bytes on the message bus, only references/keys),
  the volume-based data-in/out charges are trivial (well under $1 for
  625,000 small messages), but the **$0.04/hour x 24 x 30 ≈ $28.80/month
  per-stream floor is unavoidable and volume-independent** — the one cost
  in this whole comparison that doesn't scale to near-zero during quiet
  periods (nights, weekends, between daily-incremental runs), unlike every
  other option evaluated here.
- **Bottom line for ticket 04:** because S3/SNS/SQS/EventBridge all land
  under ~$1-2 total even at the platform's full one-time 625K-object
  historical volume, **cost is not a reason to choose coarser event
  granularity over per-object-write granularity** among those three
  substrates — the per-message cost difference between "one event per
  bronze object" (625K events) and "one event per CIK-window" (~1,250
  events at today's ~500-CIK grain) is well under a dollar either way. The
  only substrate where volume/granularity would matter for cost is Kinesis,
  and only because of its fixed per-stream floor, not because of anything
  granularity-related — and Kinesis is already ruled out on architectural
  grounds in §1.

### 4. Existing constraint check

**Verdict: no standing constraint in this repo rules out any candidate on
non-technical grounds. The ECR restriction genuinely doesn't apply (as the
ticket already suspected); no IAM boundary, permissions boundary, SCP, or
region restriction exists anywhere in this repo's Terraform or docs; and
EventBridge Pipes was previously evaluated for a *different* purpose in
this repo and explicitly not chosen for that purpose — which is worth
surfacing so it isn't mistaken for a blanket rejection of Pipes as a
technology.**

- **ECR image-management restriction (CLAUDE.md "Image management"):**
  confirmed this section only constrains *deployable image registries* —
  "Use AWS ECR only for deployable images. Do not add non-AWS registry
  targets, SDKs, ODBC drivers, or deployment steps back into this repo
  unless the platform architecture changes explicitly" (CLAUDE.md:1205-1207).
  A new SQS-drained or Pipes-triggered ECS consumer still builds and
  publishes its image to the existing shared `edgartools-<env>-images` ECR
  repository under a new tag prefix — nothing about SNS/SQS/EventBridge/
  Kinesis touches image registries at all. This map is exactly the kind of
  "platform architecture changes explicitly" case the clause's own escape
  hatch names. Not a blocker, confirmed rather than assumed.
- **No permissions boundary / IAM boundary / SCP found:** grepped
  `infra/terraform/**/*.tf` for `permissions_boundary`,
  `permission boundary`, `iam_boundary`, `SCP`, `service control policy` —
  zero hits. This account (`690839588395`) does not constrain which AWS
  services a Terraform-managed IAM role may use via any boundary policy
  found in this repo.
- **No region restriction found beyond an operational convention, not a
  technical constraint:** CLAUDE.md's `AWS_DEFAULT_REGION=us-east-1`
  env-var comment ("infra is us-east-1, not the default us-east-2") is a
  documentation note about where this account's resources already live,
  not a restriction preventing a new resource type from being created
  there — SNS, SQS, EventBridge, and Kinesis are all available in
  `us-east-1`.
- **CONTEXT.md and all three ADRs (`docs/adr/0001`-`0003`) contain no
  reference** to queues, messaging, IAM boundaries, or region restrictions
  (grepped directly; ADR 0003, the closest thematically relevant one, is
  about Snowflake-side role ownership for the gold pipeline, not AWS
  messaging infrastructure — read in full, confirmed no overlap with this
  question).
- **One real, specific prior finding worth surfacing rather than treating
  as silent:** `.planning/workstreams/fix-pipelines/milestones/v1.0-phases/03-failure-notifications/03-RESEARCH.md:458`
  states "`aws_scheduler_*` resources (EventBridge Scheduler) and
  `aws_pipes_*` (EventBridge Pipes) serve different use cases. They are NOT
  replacements for `aws_cloudwatch_event_rule` + `aws_cloudwatch_event_target`.
  The correct resources for catching Step Functions state change events and
  routing to SNS are `aws_cloudwatch_event_rule` + `aws_cloudwatch_event_target`."
  This is a real prior decision in this repo **against** using EventBridge
  Pipes — but scoped narrowly to routing already-fired AWS-service
  state-change events (Step Functions FAILED) to SNS for email alerting,
  which `aws_cloudwatch_event_rule`/`_target` already does simply. It is
  not evidence against Pipes for *this* map's actual candidate use (an SQS
  queue of bronze-write events feeding an ECS RunTask target, §2) — a
  structurally different problem (queue-draining into compute, not
  rule-matching an existing AWS event into a notification). Flagged
  explicitly so this prior note isn't misread as a blanket "no Pipes in
  this repo" constraint when it was a use-case-specific fit decision.
- **No standing constraint found against SQS or Kinesis specifically** —
  both are simply absent from this repo's Terraform today (§0), which is a
  "not yet built" fact, not a "ruled out" one.

## Verdict

1. **S3 -> SNS -> multiple SQS subscriptions is the natural extension** of
   the live precedent (§0/§1) — same resource types, additive to an
   already-Terraform-managed topic, using an AWS-documented fanout pattern
   this repo already exercises once (Snowflake's own subscription).
   EventBridge is a real alternative already operated in this account for a
   different purpose, with a genuine capability edge (content-based
   filtering) SNS can't cleanly match; it would be new *usage*, not new
   *infrastructure*. Kinesis is the only option that is genuinely new
   operational surface end to end, and its core differentiator (ordered
   replay) isn't something this map's design needs.
2. **SQS-triggered ECS Fargate is directly AWS-documented** via two real
   patterns (EventBridge Pipes -> ECS RunTask, or a long-running polling
   Fargate service) — not improvised glue. **The same SQS(+Pipes) substrate
   can serve both the N-parallel-worker and single-reducer consumption
   shapes ticket 06/09/10 need, via batch-size/batch-window configuration —
   but as two independently-configured queues fed by one SNS fan-out, not
   one shared queue.** This is a concrete, actionable answer for ticket 04:
   design the fan-out topic to publish to (at least) two queues per
   consumer-family, not one queue that every consumer type reads from.
2b. **Snowpipe Streaming is not worth adopting for the existing gold-export
   path** — the Dec-2025 Snowflake pricing simplification erased its former
   cost advantage over file-based Snowpipe, its latency win (~55s) is small
   relative to this map's actual runtime problem, and it requires replacing
   rather than extending the current Parquet/manifest write path. Carried
   forward as an option for ticket 08, not resolved here.
3. **Cost does not differentiate S3/SNS/SQS/EventBridge at this platform's
   real volume** (all under ~$2 for a full 625K-object backfill, effectively
   free at daily-incremental steady-state) — **so cost is not a reason to
   prefer coarse event granularity over per-bronze-object-write granularity**
   for ticket 04, among those three. Kinesis carries a real, volume-independent
   ~$28.80/month-per-stream floor, reinforcing §1's finding that it's the
   outlier option, not a tiebreaker among the others.
4. **No standing repo constraint rules out any candidate.** The ECR
   restriction genuinely doesn't apply (confirmed, not assumed); no IAM
   boundary/SCP/region restriction exists; a prior repo decision against
   EventBridge Pipes was scoped to an unrelated use case and doesn't
   transfer here.

**Recommendation for [Decide event granularity for bronze-write
triggers](04-decide-event-granularity.md):** this research points toward
**S3 Event Notifications -> SNS -> SQS**, with SNS fanning out to (at
minimum) two SQS queues per consumer family — one drained by
small-batch/no-window EventBridge Pipes -> ECS RunTask for parallel workers
(silver parse, per ticket 09's isolated producers), one drained by a
batched/windowed Pipes config or a long-running polling Fargate service for
the generalized-per-event reducer (ticket 09's merge step, and the
structurally identical patterns tickets 06/10 need for MDM export and graph
sync respectively). EventBridge (full event-bus, not just Pipes) stays on
the table specifically if ticket 04 wants content-based routing (e.g.
different consumers for different SEC form types) that SNS's coarser
filter policies can't express as cleanly — that's a real, not merely
theoretical, reason to reconsider EventBridge, not just a runner-up
mention. Kinesis is not recommended and shouldn't consume further
investigation time in ticket 04.

Critically, **this research does not push ticket 04 toward coarser
batching for cost or overhead reasons** — at this platform's actual event
volume, per-bronze-object-write granularity (the finest option ticket 04
lists, ~625K events for a full historical backfill and a small fraction of
that per day at steady state) is cheap enough on every viable substrate
(§3) that granularity should be decided on *architectural* grounds (what
groups naturally into one silver-write unit, what ticket 01's shard
boundaries suggest, what ticket 09's reducer needs as an accumulation unit)
rather than being pushed coarser to save messaging costs. The one place
cost *would* start to matter is if a design ever introduced Kinesis's
per-stream floor — which this research recommends against for unrelated
architectural reasons anyway, so the two findings reinforce rather than
conflict with each other.
