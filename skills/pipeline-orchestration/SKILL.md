---
name: pipeline-orchestration
description: Build and operate per-pipeline timers, dependency sequences and start/stop lifecycles on approved platforms. Use for scheduled data pipelines, efficient Step Functions and portable workflow deployment; route data preparation and recovery to their owning skills.
---

# Pipeline orchestration

Schedule, start, stop and sequence complete, qualified pipelines. Keep the
pipeline definition independent of the approved execution platform. AWS is the
first hosted implementation; local Docker is the first portability proof.
Creating a skill or configuration does not authorize deployment or activation.

## Establish the runnable pipeline

Read [data-operations](../data-operations/SKILL.md) for current delivery readiness,
load contracts and operational evidence. Inspect the selected pipeline's current
configuration, commands and deployed revision before changing it.

- **New source or domain:** route through [data-profiling](../data-profiling/SKILL.md),
  [data-quality](../data-quality/SKILL.md) and
  [data-onboarding](../data-onboarding/SKILL.md). Build the entire declared
  pipeline, including mastering and relationships; finish configuration before
  onboarding tests and proving runs. Schedule only after required qualification
  and approval/activation gates. Captured inputs do not authorize acquisition.
- **Existing approved pipeline:** reuse its approved rules and qualification
  when still applicable; check input availability, dependencies and current
  execution compatibility. Changed rules follow
  [refining-rules](../refining-rules/SKILL.md).
- **Missing capability:** identify the exact unsupported operation and smallest
  blocking behavior. Route engine/store work to
  [mdm-engineering](../mdm-engineering/SKILL.md) or
  [data-platform](../data-platform/SKILL.md); qualify that gap separately before
  freezing the pipeline. State what remains unsupported; never invent a CLI.

## Keep execution ownership intact

[Bookkeeping](../bookkeeping/SKILL.md) owns execution state, immutable run inputs,
leases/fencing, checkpoints, retry/recovery and verified completion.
[Change Journal](../change-journal/SKILL.md) owns published changes and delivery
receipts. Use their normal interfaces and authorization. Platform task status
alone is not verified pipeline completion.

Use the existing control boundary to coalesce overlapping triggers into at most
one pending run; preserve in-flight input pins. If that boundary cannot express
the requested behavior, record and route the gap before enabling its timer.
Do not build another queue, run ledger, checkpoint system or shutdown protocol.
Configure dependency order and concurrency; keep independent healthy pipelines
running when an affected pipeline or dependent is blocked.

## Configure before deployment

Use the existing pipeline/configuration path where supported. Record the
following operational requirements there or in its operational record; this
list is not a new executable schema:

- Pipeline identity, owner, approved configuration/version and qualified worker
  command/image; immutable input references and completion verifier.
- Its own schedule, timezone, deadline, missed-trigger policy and enabled state.
  For business-day timing, name the business calendar and holiday behavior;
  a weekday cron alone does not implement a holiday calendar.
- Required dependencies, global/per-pipeline concurrency and overlap coalescing.
- Start/stop and bounded failure policy delegated to existing control; distinguish
  infrastructure launch retries from work retries so attempts do not multiply.
- Resource profile, budget, telemetry references and approved platform binding.
  Keep business rules/source names out of orchestration logic.
- Scoped deployment/removal inventory, authorization and retained durable assets.

A source-sequence wiring check is an offline configuration check, not a due-work
selector or runtime readiness test. A load command processes a captured delivery;
it does not implement a universal timer or dispatcher. Discover actual support
before proposing rollout. Read [AWS execution](references/aws-execution.md) for
Step Functions and AWS lifecycle work.

## Prove and operate

1. Validate configuration references, acyclic dependency order and runnable
   worker contracts. Test the selected platform definition offline where possible.
2. Prove the same frozen configuration and retained input on local Docker and
   AWS through their supported interfaces: start, verified completion, duplicate
   trigger, affected failure isolation, bounded retry, stop and unchanged replay.
   Reuse applicable evidence; do not claim an unrun platform is qualified.
3. Check stop semantics on both the workflow and underlying compute. Disable
   future triggers first, then use supported owner/platform stop operations and
   confirm the scoped work actually stopped. Preserve durable recovery evidence.
4. For removal/recreation, inventory exactly the timer/workflow/compute bindings
   being removed and retained captures, stores, receipts and secrets. Obtain the
   applicable destructive-action approval. Recreate from committed configuration
   on the approved target, requalify and obtain activation approval before enabling.
5. Report configuration/qualification/approval/activation separately. A green
   syntax check or test does not switch anything on.

Choose the lowest total cost meeting configured deadlines and correctness.
For resource/throughput decisions use
[compute economics](../production-support/references/compute-economics.md).
Use [production-support](../production-support/SKILL.md) for alerts, CPU/memory/log
analysis and holistic diagnosis. Monitoring and scheduling are ordinary platform
jobs; AI investigations run only on alerts or scheduled reviews, with bounds.
