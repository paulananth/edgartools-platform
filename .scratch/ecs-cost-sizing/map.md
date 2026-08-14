# ECS and Step Functions Value, Cost, and Throughput Optimization

Label: `wayfinder:map`

## Destination

After Claude's current work completes, produce an evidence-backed optimization
policy and rollout handoff for the `edgartools-prod` ECS and Step Functions
portfolio. Every workflow must have a keep, merge, reshape, reschedule, or
retire rationale; every loop must expose its item unit, record funnel,
concurrency, retries, duration, and unit cost; and every ECS stage must select
an intentional machine profile with correctness, utilization, throughput,
end-to-end completion speed, cost, canary, and rollback gates.

## Notes

- This map is planning-only. It does not change ECS, Step Functions, task
  definitions, deployment scripts, or Claude's work.
- Scope is AWS account `690839588395`, region `us-east-1`, cluster
  `edgartools-prod-warehouse`, and `edgartools-prod-*` workflows.
- Wait for Claude's explicit completion/handoff before treating the deployed
  ECS/workflow inventory as canonical. Re-query live state after handoff.
- A **workload class** is the operation; a **task profile** is its CPU/memory
  reservation; an **execution** is one launched Fargate task or Step Functions
  run. A task-definition revision is not itself a running cost center.
- A **workflow** is one production Step Functions state machine. A **stage** is
  one value-producing, validation, orchestration, or recovery step within it.
- A **loop** is either a Step Functions `Map`/Distributed Map or an internal
  CLI batch iteration. Its **loop item** is the declared unit of scheduling,
  such as a CIK batch, CIK window, accession, relationship type, partition, or
  generation shard.
- **Records processed** is never a single ambiguous counter. Each measured
  record funnel distinguishes selected, attempted, successfully parsed,
  committed, exported, skipped-idempotent, rejected, retried, and deduplicated
  records, where those dispositions apply.
- **Workflow value** is the required data product, integrity gate, recovery
  capability, or operator control consumed downstream. A workflow with no
  unique output, consumer, safety role, or cheaper execution path is a
  consolidation or retirement candidate.
- **Completion speed** is wall-clock time from workflow trigger to a durable,
  complete, validated output that its consumer can use. A fast ECS stage does
  not count as a speed improvement if downstream retries, reconciliation, or
  failed gates make the end-to-end workflow slower or incomplete.
- **Unit economics** includes cost per successful execution and, where record
  counts are meaningful, cost per 1,000 committed records and per 1,000
  exported records. End-to-end completion time, records per second, and state
  transitions are reported alongside ECS vCPU-hours and GB-hours so cost
  reductions cannot hide a slower critical path.
- Historical profile evidence is captured in
  [`history-right-sizing-2026-08-09.md`](history-right-sizing-2026-08-09.md).
- Before implementation, use `/gof-refactor-reviewer`, then repository test and
  code-review gates.

### Live baseline captured 2026-08-08/09

- The cluster has no ECS services; Fargate spend comes from standalone tasks.
- One task was running: `edgartools-prod-mdm-medium:138`, `1 vCPU / 4 GiB`,
  command `mdm run --entity-type all`.
- Production profiles: `small` `512/1024`, `medium` `1024/4096`, `large`
  `2048/8192`, with corresponding MDM families.
- Latest Container Insights observations in the 2026-08-01 through 2026-08-09
  window: `mdm-large` CPU ~20% / memory ~2%; `mdm-medium` CPU ~17% / memory
  ~13%; warehouse `medium` CPU 100% / memory ~16%; warehouse `large` CPU ~89%
  / memory ~9%.
- These identify candidates, not automatic downgrades: historical notes record
  OOM failures for full-universe/security workloads at lower memory sizes.
- Live prod task-definition profiles currently referenced by Step Functions are
  `small:159` (`512/1024`), `medium:164` (`1024/4096`), `large:157`
  (`2048/8192`), `mdm-small:137` (`512/1024`), `mdm-medium:138`
  (`1024/4096`), and `mdm-large:72` (`2048/8192`).
- Step Functions pin those revision ARNs directly. The same workload family is
  selected through multiple code paths: `workflow_profile()`,
  `task_definition_for_mdm_workflow()`, and separate state-machine generators.
  `workflow_profile()` explicitly documents dead `daily_incremental` and
  `bootstrap` cases while their live definitions use `large` directly.
- The live map includes 26 prod state machines, with profile assignments that
  are broadly intentional but not represented by one canonical workload
  contract. Verification commands generally use `mdm-small`, ordinary MDM
  stages use `mdm-medium`, and residual-holds heavy stages use `mdm-large`.

## Decisions so far

<!-- Closed ticket decisions: one-line gist and link; detail stays in the ticket. -->

- [Decide the Workflow Value Test and Optimization Objective](issues/10-decide-workflow-value-and-optimization-objective.md) — Correctness/recovery and end-to-end completion speed are co-primary; retain workflows only for evidenced output or operator value, then optimize cost from measured baselines.
- [Fix Stage1BEntityFacts's OOM on the `medium` Task Profile](issues/20-fix-stage1b-entity-facts-oom-on-medium-profile.md) — Root cause was the shared silver-publish merge step's unchunked cold-start delta materialization (~4.3GB), not the entity-facts fetch loop (already streams); fixed and deployed to prod (PR #416): all three Stage1B modes moved to `large`, plus a structural phase-1-SQL/phase-2-chunked rewrite of `merge_candidate_into_canonical`. Does not retroactively cover the in-flight `retry7` execution.

## Not yet specified

- Schedule and trigger cadence changes that become visible only after the
  workflow portfolio's consumers, freshness requirements, and overlap are
  established.
- Exact savings target and implementation wave boundaries; these depend on the
  measured workflow unit-economics baseline and the workflows retained.
- Whether any remaining low-volume orchestration should move away from
  Standard Step Functions; feasibility depends on its ECS integration pattern,
  duration, audit requirements, and execution history.

## Out of scope

- Editing, reverting, staging, or merging Claude's work.
- Stopping tasks or changing live definitions during planning.
- Reducing correctness, coverage, release gates, or MDM safety for cost alone.
- Optimizing Snowflake warehouses, dbt models, S3 retention, or dashboard query
  cost except where their existing outputs establish a workflow's consumer or
  value.
