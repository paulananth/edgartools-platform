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

- [Confirm Post-Claude ECS Baseline and Ownership Boundary](issues/01-confirm-post-claude-ecs-baseline.md) — Handoff is complete; 26 workflows consistently reference six immutable task definitions, while 466 additional active revisions require guarded reference and rollback review before cleanup.
- [Measure ECS Utilization by Workload Class](issues/02-measure-utilization-by-workload-class.md) — Task-bound evidence validates BatchSilver medium/20 and large for combined daily/full-universe work; MDM medium remains necessary, while MDM large and standalone gold need representative medium canaries before resizing.
- [Decide Sizing Safety Floors and Utilization Bands](issues/03-decide-workload-to-profile-policy.md) — Classify immutable workload/input identities with asymmetric CPU/memory bands, a 5% p95 speed guardrail, two normal or three high-risk canaries, and explicit floors that retain large for combined daily work and pending residual/gold canaries.
- [Decide ECS Sizing Canary, Rollback, and Drift Gates](issues/04-decide-canary-and-drift-gates.md) — Isolate stage-scoped canaries, require correctness plus speed and material cost improvement, preserve exact configuration rollback through a workload-counted bake window, and fail closed on hard failures, identity drift, or missing task-bound evidence.
- [Reconcile Prod Task Definitions and Step Functions References](issues/05-reconcile-prod-task-definitions-and-step-function-references.md) — The live six-revision cohort is internally consistent; 458 revisions are provisional retirement candidates, but cleanup waits for an explicit protected rollback cohort and fresh exact-ARN reference audit.
- [Decide a Single Prod Workload-to-Profile Contract](issues/06-decide-single-prod-workload-profile-contract.md) — Use one portable, versioned workload-class registry and fail-closed resolver, separate runtime from shared resource tiers, and switch all generated ECS states atomically without dual profile authority.
- [Standardize Step Functions Concurrency and Failure Controls](issues/07-standardize-step-function-concurrency-and-failure-controls.md) — Target 8-20 only for parallel-safe fan-out, retain evidence-backed correctness caps below 8, enforce the smaller of a 32-vCPU ceiling and the live quota after 20% reserve, and fail closed on retries, timeouts, tolerated failures, completeness, admission, or definition drift.
- [Retire Stale Prod Revisions and Add Drift Gates](issues/08-retire-stale-prod-revisions-and-add-drift-gates.md) — Reused the durable rollback registry and pure reconciliation boundary; added exact current-cohort/reference drift gates, a shared deploy-cleanup lock, reproducible state-bound plan hashes, and batched exact-ARN re-audits. A live read-only check found 836 stale ACTIVE revisions with zero reference drift but correctly blocked retirement because only one of three verified cohorts exists.
- [Decide Warehouse Versus MDM Profile Families](issues/09-decide-warehouse-vs-mdm-profile-families.md) — Retain isolated warehouse and MDM Runtime Variants over shared resource tiers, pair their exact identities in every production release, keep full-canonical seed on warehouse large, and retire MDM large only after accepted non-zero-data medium canaries and bake protection.
- [Decide the Workflow Value Test and Optimization Objective](issues/10-decide-workflow-value-and-optimization-objective.md) — Correctness/recovery and end-to-end completion speed are co-primary; retain workflows only for evidenced output or operator value, then optimize cost from measured baselines.
- [Inventory Every Production Workflow and Consumer](issues/11-inventory-every-production-workflow-and-consumer.md) — Independent re-verification confirmed the draft (26→25 live machines, 8 not 9 zero-execution workflows), sharpened the graph-candidate gap, and surfaced a real production failure-masking mechanism plus a Step-Functions-bypass blind spot; operator decided: deregister the 7 orphaned MDM machines, accept the SFN-bypass path, add visibility (not blocking) to the `MdmVerify` mask, and default dormant workflows to retirement candidates.
- [Measure Every Loop and Record Funnel](issues/12-measure-every-loop-and-record-funnel.md) — Full item-vs-record inventory across 8 loop types from real executions (up to ~1,850x item-to-record multipliers); surfaced a second, independent failure-masking instance (a `FAILED` execution that still committed ~21M gold rows), a Distributed-Map traceability gap (child `run_id`s are UUIDs uncorrelated to the parent), and that `daily_incremental`/`silver_mdm_gold`/`generation_build` have little-to-no recent execution evidence.
- [Build Workflow Unit Economics](issues/13-build-workflow-unit-economics.md) — Exact per-execution Fargate/Step-Functions/CloudWatch costing for 17 of 26 workflows (9 genuinely $0, never run); separated fixed-orchestration workflows (`gold_refresh` ~$0.005/invocation regardless of volume) from record-scaling ones (`load_history`'s network-bound silver rows at $9.46/1,000 vs. `bronze_seed_silver_gold`'s reprocessing-only $0.787/1,000, a 12x gap from I/O not profile); traced `load_history` retry5's masked-success failure to a specific uncaught bookkeeping step (`WriteRunSummary`) failing after the real output was already committed, and found a second, genuine zero-commit failure (`bronze_seed_silver_gold`'s `mdm export`, no `Catch`) as its mirror image.
- [Decide the Production Workflow Portfolio](issues/14-decide-the-production-workflow-portfolio.md) — `bronze_seed_silver_gold` is the sole canonical composite chain (`silver_mdm_gold`/`mdm_gold` retired); 4 more zero-execution machines retired (`bootstrap_full`, `catch_up_daily_form_index`, `load_daily_form_index_for_date`, `mdm_seed_universe`) but `full_reconcile` kept as a protected disaster-recovery capability despite zero use; `generation_build` kept as the portfolio's only graph-generation capability; `residual_holds_graph` reshaped to add the same non-blocking `Catch` the other 5 `MdmVerify` machines already have; a `verify_status` marker proposed to stop three tickets' worth of hand-deriving `Catch` outcomes from raw Step Functions history. `ownership_mdm_gold`'s and `generation_build`'s own status split into [Ticket 26](issues/26-confirm-ownership-mdm-gold-intended-scope.md) and [Ticket 27](issues/27-confirm-generation-build-was-not-abandoned.md).
- [Decide the Loop, Batch, and Concurrency Policy](issues/15-decide-loop-batch-and-concurrency-policy.md) — Six loop classes decided: `load_history`'s CIK-window loop needs opt-in cross-run resume (`--resume-ledger-run-id`, mirrors `BatchSilver`'s precedent, follow-up PR) since retries currently redo already-captured discovery from scratch; filing/accession and verification ratified as-is; relationship-type backfill stays sequential; `generation_build`'s partition concurrency deferred to Ticket 14's retain/retire call; `mdm sync-graph`'s 200-row default limit — never exceeded in any observed execution against a ~193K-node real graph — should raise to unbounded for production runs, pending one canary (folded into Ticket 16).
- [Decide the Machine Profile for Every Workflow Stage](issues/16-decide-machine-profile-per-workflow-stage.md) — Closed Ticket 06's initial 10-class matrix against Ticket 12/13's evidence: `mdm.full`'s current-digest confirmation flagged as provisionally satisfied (81% peak memory, unverified image currency); two long-pending downgrade canaries (`mdm.residual_security`, `warehouse.gold_standalone`) scheduled as [Ticket 28](issues/28-run-mdm-residual-security-medium-canaries-and-unbounded-graph-sync-canary.md)/[Ticket 29](issues/29-run-warehouse-gold-standalone-medium-canaries.md), still zero done; a new `mdm-large`-first canary policy set for Ticket 15's unbounded `sync-graph` decision (folded into Ticket 28); `warehouse.full_canonical_seed` retired as a separate class now that `Stage0CompanyIdentity`'s `large` floor moved into `WindowedBootstrap` intact.
- [Decide the Execution and Loop Telemetry Contract](issues/17-decide-execution-and-loop-telemetry-contract.md) — Codified fixes for every instrumentation gap Tickets 11-13 hit by hand: durable manifests (not CloudWatch's 7-day logs) become the ledger of record; Distributed Map children must propagate their parent's execution name to close the biggest child-traceability gap found; missing record-count fields fail schema validation rather than reading as zero; a `triggered_via` field keeps the accepted Step-Functions-bypass path visible instead of silently invisible. MDM's missing per-run binding columns split out as real schema work into [Ticket 30](issues/30-add-per-run-binding-columns-to-mdm-tables.md).
- [Decide Step Functions Structural Simplification](issues/18-decide-step-functions-structural-simplification.md) — One shared ECS-task-state builder replaces the 8 hand-rolled copies Ticket 11's GoF review found, with retry/Catch policy as a required parameter (closing the exact class of gap that let `residual_holds_graph` silently miss its `Catch`); Standard execution type settled outright everywhere, no exceptions; no further merging of retained machines beyond shared generation code — `bootstrap`/`daily_incremental`/`load_history`'s different trigger/scope semantics are real, not just config knobs.
- [Decide the Optimization Rollout and Acceptance Gates](issues/19-decide-optimization-rollout-and-acceptance-gates.md) — Five-wave rollout (telemetry → portfolio retirement → loop/concurrency → machine profile → structural simplification), gated behind a new Wave 0 hard prerequisite ([Ticket 23](issues/23-decide-and-capture-protected-rollback-cohort.md)'s then-still-undecided protected rollback cohort) that this ticket surfaced rather than assumed; a new Structural/Behavior Canary generalizes Ticket 04's profile-canary isolation mechanism to correctness/output-parity gates for the four non-profile waves; never-redrive and speed-as-co-equal-gate rules apply across every wave. Wave 5's missing staged-transaction deploy infrastructure split out as [Ticket 31](issues/31-build-staged-transaction-deploy-support.md).
- [Fix Stage1BEntityFacts's OOM on the `medium` Task Profile](issues/20-fix-stage1b-entity-facts-oom-on-medium-profile.md) — Root cause was the shared silver-publish merge step's unchunked cold-start delta materialization (~4.3GB), not the entity-facts fetch loop (already streams); fixed and deployed to prod (PR #416): all three Stage1B modes moved to `large`, plus a structural phase-1-SQL/phase-2-chunked rewrite of `merge_candidate_into_canonical`. Does not retroactively cover the in-flight `retry7` execution.
- [Fix `ToleratedFailurePercentage: 0` Zeroing Out Entity-Facts/Per-Filing/13F Coverage](issues/21-fix-toleratedfailurepercentage-zeroing-out-entity-facts-per-filing-13f.md) — Live evidence: retry7 added zero net new rows to `SEC_FINANCIAL_FACT`/`EARNINGS_RELEASE`/`EXECUTIVE_RECORD` (coverage 0.04%–1.7% of the 51,888-CIK universe) because window 1's failure aborted all 51 remaining windows under `ToleratedFailurePercentage: 0`. Scoped fix: raise tolerance to 15% now (stopgap, all three Maps), move failure handling inside the per-window `ItemProcessor` as a follow-up structural fix. Not yet implemented — awaiting go-ahead.
- [Research: Steady-State AWS Cost Under $1/day, and Why Silver Is a Monolithic DuckDB File](issues/22-research-steady-state-aws-cost-under-a-dollar-and-silver-db-size.md) — No NAT Gateway; steady state is ~$2.00–2.10/day, entirely S3 (cross-checked live vs. Cost Explorer). Root cause: `warehouse/silver/`'s versioned keys have no S3 lifecycle rule (unlike `silverstage/`, which already has one), so 1.34 TB of dead noncurrent versions have accumulated (~$1.05/day). Extending the existing lifecycle rule alone reaches ~$0.95–1.10/day, no architecture change needed. Silver's 1.5GB size: a sharded *write* path already exists but is wired to only one secondary command (`bootstrap-batch`); every primary ingestion command still `shutil.copy2()`s the whole canonical file per publish. Four architectural options presented, none chosen (research-only).
- [Decide and Capture the Protected Rollback Cohort](issues/23-decide-and-capture-protected-rollback-cohort.md) — Adopted a Configuration Rollback cohort (current six task-definition revisions plus a canonically identical earlier six-revision cohort) as an immediate, cheap baseline; confirmed nothing today satisfies a separate, genuinely-validated Code Rollback requirement, split out as Ticket 32. Satisfied Ticket 19's Wave 0 hard prerequisite as of 2026-08-12. **Stale as of this recovery (2026-08-28):** the specific revision numbers this ticket captured (warehouse `small:181`/`medium:186`/`large:178`, MDM `small:158`/`medium:158`/`large:92`) are almost certainly superseded by deploys since, including this session's own accounting-flag-fix deploy — re-capture the cohort before relying on it.
- [Validate the Proposed Rollback Cohort Evidence](issues/24-validate-proposed-rollback-cohort-evidence.md) — Rejected the pre-handoff image pair as known-good: its only exact-window execution failed before graph/gold, while canonically identical prior copies of the current six definitions remain viable control-plane recovery candidates pending operator designation.
- [WriteRunSummary Hand-Built S3 Path: Root Cause, Fix, and Portfolio-Wide Check](issues/25-write-run-summary-hand-built-path-decoupling.md) — Root-caused `load_history` retry5's terminal-state failure (real work completed, bookkeeping step died on a hand-built S3 key) and checked the retained portfolio for the same shape.
- [Confirm `ownership_mdm_gold`'s Intended Scope](issues/26-confirm-ownership-mdm-gold-intended-scope.md) — Deliberate, not abandoned: the machine's own source comments and its introducing commit (`02173c80`, "Ticket 21 insider load is person + IS_INSIDER only") confirm it's a purpose-built skip of full company MDM re-resolution for insider-only ownership updates. Keep, with a distinct documented scope alongside `bronze_seed_silver_gold` — closes the one item Ticket 14 left open.
- [Confirm `generation_build` Was Not Abandoned](issues/27-confirm-generation-build-was-not-abandoned.md) — Not abandoned, genuinely rare-by-design: the module's own content-addressed-reuse docstring, its `rule_version`/`schema_version` defaults unchanged from `"v1"` since introduction (the one trigger for a rebuild has simply never fired), and a separate consolidation effort deliberately preserving it as structurally distinct just 3 days before this ticket all converge on the same answer. Keep, fully settled. Unblocks Ticket 15's deferred `BuildPartitions` sizing work whenever warranted.
- [Run `mdm.residual_security` Medium Canaries and the Unbounded `sync-graph` Canary](issues/28-run-mdm-residual-security-medium-canaries-and-unbounded-graph-sync-canary.md) — Accepted the current-image unbounded large sync canary, but rejected the residual-security medium downgrade: repeated executions grew active relationship counts, the shared `COMPANY_HOLDS` target made the later large control process a materially different funnel, and recovery remained unproven. Retain `mdm-large`; no production reference or bake-window change.

Tickets 01-27 above were recovered 2026-08-28 from an orphaned worktree
branch (`claude/backup-ecs-cost-sizing-worktree-2026-08-12`), renumbered
where the branch's own continuation past Ticket 19 (20-29) collided with
this map's independently-resolved reactive fixes 20-22 already on `main`
(OOM fix, `ToleratedFailurePercentage` fix, cost research — content
unrelated to the branch's rollback-cohort/ownership-scope chain; neither
side depends on the other). See each renumbered ticket for its original
branch-ticket identity if cross-referencing old notes. Tickets 28-32
(branch's own 25-29) were **not** resolved on the recovered branch. Ticket 28
has since been resolved by rejecting the MDM downgrade after live canaries;
Tickets 29-32 remain real, already-sharp open/claimed child tickets
(gold-standalone canaries, per-run binding columns, staged-transaction deploy
support, and a rehearsed Code Rollback cohort), not fog — pick them up directly
from `issues/`, same as any other frontier ticket.

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
