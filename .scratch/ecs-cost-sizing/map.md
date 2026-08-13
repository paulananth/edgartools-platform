# ECS and Step Functions Value, Cost, and Throughput Optimization

Label: `wayfinder:map`

## Destination

Produce an evidence-backed optimization policy and rollout handoff for the
`edgartools-prod` ECS and Step Functions
portfolio. Every workflow must have a keep, merge, reshape, reschedule, or
retire rationale; every loop must expose its item unit, record funnel,
concurrency, retries, duration, and unit cost; and every ECS stage must select
an intentional machine profile with correctness, utilization, throughput,
end-to-end completion speed, cost, canary, and rollback gates.

## Notes

- Latest Claude handoff after the 2026-08-11 PR #401 resync: read
  [`HANDOFF-codex-to-claude-2026-08-11-2000.md`](HANDOFF-codex-to-claude-2026-08-11-2000.md)
  before continuing Ticket 11 or treating the historical 26-workflow inventory
  as current. It links to the full earlier decision handoff.
- Silver-storage architecture (S3 cost, `load_history`'s `bootstrap-next`
  monolith-hydrate gap found live while investigating retry6's per-row cost)
  is out of this map's own scope but was substantial enough to spawn its own
  effort: see [silver-snowflake-migration](../silver-snowflake-migration/map.md).
  Treat that map's findings as evidence, not something to re-derive here.
- This map is planning-only. It does not change ECS, Step Functions, task
  definitions, deployment scripts, or Claude's work.
- Scope is the operator-selected production AWS account, configured region,
  production ECS cluster, and production Step Functions portfolio. Live
  identities belong in generated manifests and evidence, not source policy.
- The operator confirmed Claude's handoff complete on 2026-08-09. The canonical
  post-handoff inventory is linked from **Confirm Post-Claude ECS Baseline and
  Ownership Boundary**; re-query live state before any rollout or cleanup.
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

### Live baseline captured after handoff on 2026-08-09

- The cluster has no ECS services; Fargate spend comes from standalone tasks.
- No ECS service, running task, or pending task was present at the baseline
  capture. A later Ticket 07 read-only recheck found one running 1-vCPU medium
  task, demonstrating why admission must use live reservations rather than the
  baseline snapshot.
- Production profiles: `small` `512/1024`, `medium` `1024/4096`, `large`
  `2048/8192`, with corresponding MDM families.
- Latest Container Insights observations in the 2026-08-01 through 2026-08-09
  window: `mdm-large` CPU ~20% / memory ~2%; `mdm-medium` CPU ~17% / memory
  ~13%; warehouse `medium` CPU 100% / memory ~16%; warehouse `large` CPU ~89%
  / memory ~9%.
- These identify candidates, not automatic downgrades: historical notes record
  OOM failures for full-universe/security workloads at lower memory sizes.
- A later Ticket 09 read-only recheck confirmed that the three active
  full-canonical SeedUniverse states use warehouse large after a live medium
  OOM. The dormant batched workflow remains on medium without production
  execution evidence and is not sizing evidence.
- Live prod task-definition profiles referenced by all 26 Step Functions are
  `small:166` (`512/1024`), `medium:170` (`1024/4096`), `large:163`
  (`2048/8192`), `mdm-small:143` (`512/1024`), `mdm-medium:143`
  (`1024/4096`), and `mdm-large:77` (`2048/8192`).
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
- [Confirm Post-Claude ECS Baseline and Ownership Boundary](issues/01-confirm-post-claude-ecs-baseline.md) — Handoff is complete; 26 workflows consistently reference six immutable task definitions, while 466 additional active revisions require guarded reference and rollback review before cleanup.
- [Reconcile Prod Task Definitions and Step Functions References](issues/05-reconcile-prod-task-definitions-and-step-function-references.md) — The live six-revision cohort is internally consistent; 458 revisions are provisional retirement candidates, but cleanup waits for an explicit protected rollback cohort and fresh exact-ARN reference audit.
- [Validate the Proposed Rollback Cohort Evidence](issues/21-validate-proposed-rollback-cohort-evidence.md) — Reject the pre-handoff image pair as known-good: its only exact-window execution failed before graph/gold, while canonically identical prior copies of the current six definitions remain viable control-plane recovery candidates pending operator designation.
- [Measure ECS Utilization by Workload Class](issues/02-measure-utilization-by-workload-class.md) — Task-bound evidence validates BatchSilver medium/20 and large for combined daily/full-universe work; MDM medium remains necessary, while MDM large and standalone gold need representative medium canaries before resizing.
- [Decide Sizing Safety Floors and Utilization Bands](issues/03-decide-workload-to-profile-policy.md) — Classify immutable workload/input identities with asymmetric CPU/memory bands, a 5% p95 speed guardrail, two normal or three high-risk canaries, and explicit floors that retain large for combined daily work and pending residual/gold canaries.
- [Decide ECS Sizing Canary, Rollback, and Drift Gates](issues/04-decide-canary-and-drift-gates.md) — Isolate stage-scoped canaries, require correctness plus speed and material cost improvement, preserve exact configuration rollback through a workload-counted bake window, and fail closed on hard failures, identity drift, or missing task-bound evidence.
- [Decide a Single Prod Workload-to-Profile Contract](issues/06-decide-single-prod-workload-profile-contract.md) — Use one portable, versioned workload-class registry and fail-closed resolver, separate runtime from shared resource tiers, and switch all generated ECS states atomically without dual profile authority.
- [Standardize Step Functions Concurrency and Failure Controls](issues/07-standardize-step-function-concurrency-and-failure-controls.md) — Target 8-20 only for parallel-safe fan-out, retain evidence-backed correctness caps below 8, enforce the smaller of a 32-vCPU ceiling and the live quota after 20% reserve, and fail closed on retries, timeouts, tolerated failures, completeness, admission, or definition drift.
- [Decide Warehouse Versus MDM Profile Families](issues/09-decide-warehouse-vs-mdm-profile-families.md) — Retain isolated warehouse and MDM Runtime Variants over shared resource tiers, pair their exact identities in every production release, keep full-canonical seed on warehouse large, and retire MDM large only after accepted non-zero-data medium canaries and bake protection.
- [Inventory Every Production Workflow and Consumer](issues/11-inventory-every-production-workflow-and-consumer.md) — Independent re-verification confirmed the draft (26→25 live machines, 8 not 9 zero-execution workflows), sharpened the graph-candidate gap, and surfaced a real production failure-masking mechanism plus a Step-Functions-bypass blind spot; operator decided: deregister the 7 orphaned MDM machines, accept the SFN-bypass path, add visibility (not blocking) to the `MdmVerify` mask, and default dormant workflows to retirement candidates.
- [Measure Every Loop and Record Funnel](issues/12-measure-every-loop-and-record-funnel.md) — Full item-vs-record inventory across 8 loop types from real executions (up to ~1,850x item-to-record multipliers); surfaced a second, independent failure-masking instance (a `FAILED` execution that still committed ~21M gold rows), a Distributed-Map traceability gap (child `run_id`s are UUIDs uncorrelated to the parent), and that `daily_incremental`/`silver_mdm_gold`/`generation_build` have little-to-no recent execution evidence.
- [Build Workflow Unit Economics](issues/13-build-workflow-unit-economics.md) — Exact per-execution Fargate/Step-Functions/CloudWatch costing for 17 of 26 workflows (9 genuinely $0, never run); separated fixed-orchestration workflows (`gold_refresh` ~$0.005/invocation regardless of volume) from record-scaling ones (`load_history`'s network-bound silver rows at $9.46/1,000 vs. `bronze_seed_silver_gold`'s reprocessing-only $0.787/1,000, a 12x gap from I/O not profile); traced `load_history` retry5's masked-success failure to a specific uncaught bookkeeping step (`WriteRunSummary`) failing after the real output was already committed, and found a second, genuine zero-commit failure (`bronze_seed_silver_gold`'s `mdm export`, no `Catch`) as its mirror image.
- [Decide the Loop, Batch, and Concurrency Policy](issues/15-decide-loop-batch-and-concurrency-policy.md) — Six loop classes decided: `load_history`'s CIK-window loop needs opt-in cross-run resume (`--resume-ledger-run-id`, mirrors `BatchSilver`'s precedent, follow-up PR) since retries currently redo already-captured discovery from scratch; filing/accession and verification ratified as-is; relationship-type backfill stays sequential; `generation_build`'s partition concurrency deferred to Ticket 14's retain/retire call; `mdm sync-graph`'s 200-row default limit — never exceeded in any observed execution against a ~193K-node real graph — should raise to unbounded for production runs, pending one canary (folded into Ticket 16).
- [Decide the Production Workflow Portfolio](issues/14-decide-the-production-workflow-portfolio.md) — `bronze_seed_silver_gold` is the sole canonical composite chain (`silver_mdm_gold`/`mdm_gold` retired); 4 more zero-execution machines retired (`bootstrap_full`, `catch_up_daily_form_index`, `load_daily_form_index_for_date`, `mdm_seed_universe`) but `full_reconcile` kept as a protected disaster-recovery capability despite zero use; `generation_build` kept as the portfolio's only graph-generation capability; `residual_holds_graph` reshaped to add the same non-blocking `Catch` the other 5 `MdmVerify` machines already have; a `verify_status` marker proposed to stop three tickets' worth of hand-deriving `Catch` outcomes from raw Step Functions history. `ownership_mdm_gold`'s and `generation_build`'s own status split into Tickets 23/24.
- [Decide the Machine Profile for Every Workflow Stage](issues/16-decide-machine-profile-per-workflow-stage.md) — Closed Ticket 06's initial 10-class matrix against Ticket 12/13's evidence: `mdm.full`'s current-digest confirmation flagged as provisionally satisfied (81% peak memory, unverified image currency); two long-pending downgrade canaries (`mdm.residual_security`, `warehouse.gold_standalone`) scheduled as Tickets 25/26, still zero done; a new `mdm-large`-first canary policy set for Ticket 15's unbounded `sync-graph` decision (folded into Ticket 25); `warehouse.full_canonical_seed` retired as a separate class now that `Stage0CompanyIdentity`'s `large` floor moved into `WindowedBootstrap` intact.
- [Decide the Execution and Loop Telemetry Contract](issues/17-decide-execution-and-loop-telemetry-contract.md) — Codified fixes for every instrumentation gap Tickets 11-13 hit by hand: durable manifests (not CloudWatch's 7-day logs) become the ledger of record; Distributed Map children must propagate their parent's execution name to close the biggest child-traceability gap found; missing record-count fields fail schema validation rather than reading as zero; a `triggered_via` field keeps the accepted Step-Functions-bypass path visible instead of silently invisible. MDM's missing per-run binding columns split out as real schema work into Ticket 27.
- [Decide Step Functions Structural Simplification](issues/18-decide-step-functions-structural-simplification.md) — One shared ECS-task-state builder replaces the 8 hand-rolled copies Ticket 11's GoF review found, with retry/Catch policy as a required parameter (closing the exact class of gap that let `residual_holds_graph` silently miss its `Catch`); Standard execution type settled outright everywhere, no exceptions; no further merging of retained machines beyond shared generation code — `bootstrap`/`daily_incremental`/`load_history`'s different trigger/scope semantics are real, not just config knobs.
- [Decide the Optimization Rollout and Acceptance Gates](issues/19-decide-optimization-rollout-and-acceptance-gates.md) — Five-wave rollout (telemetry → portfolio retirement → loop/concurrency → machine profile → structural simplification), gated behind a new Wave 0 hard prerequisite (Ticket 20's still-undecided rollback cohort) that this ticket surfaced rather than assumed; a new Structural/Behavior Canary generalizes Ticket 04's profile-canary isolation mechanism to correctness/output-parity gates for the four non-profile waves; never-redrive and speed-as-co-equal-gate rules apply across every wave. Wave 5's missing staged-transaction deploy infrastructure split out as Ticket 28.
- [Decide and Capture the Protected Rollback Cohort](issues/20-decide-and-capture-protected-rollback-cohort.md) — Adopted now, live-captured: current six task-definition revisions (`small:181`/`medium:186`/`large:178` warehouse, `small:158`/`medium:158`/`large:92` MDM) as the release baseline, plus a confirmed-still-ACTIVE, still-canonically-identical earlier six-revision cohort as Configuration Rollback. A genuinely validated Code Rollback cohort — real work, nothing today qualifies per Ticket 21 — split out as Ticket 29, not a blocker for the rollout. Satisfies Ticket 19's Wave 0 hard prerequisite; the rollout may now proceed.
- [Confirm `ownership_mdm_gold`'s Intended Scope](issues/23-confirm-ownership-mdm-gold-intended-scope.md) — Deliberate, not abandoned: the machine's own source comments and its introducing commit (`02173c80`, "Ticket 21 insider load is person + IS_INSIDER only") confirm it's a purpose-built skip of full company MDM re-resolution for insider-only ownership updates. Keep, with a distinct documented scope alongside `bronze_seed_silver_gold` — closes the one item Ticket 14 left open.
- [Confirm `generation_build` Was Not Abandoned](issues/24-confirm-generation-build-was-not-abandoned.md) — Not abandoned, genuinely rare-by-design: the module's own content-addressed-reuse docstring, its `rule_version`/`schema_version` defaults unchanged from `"v1"` since introduction (the one trigger for a rebuild has simply never fired), and a separate consolidation effort deliberately preserving it as structurally distinct just 3 days before this ticket all converge on the same answer. Keep, fully settled. Unblocks Ticket 15's deferred `BuildPartitions` sizing work whenever warranted.

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
