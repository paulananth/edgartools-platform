Type: research
Status: resolved

## Question

Does AWS Step Functions' native `RedriveExecution` API fit this platform's
Step Functions shape well enough to replace full `start-execution` restarts
for stopped/failed long-running pipelines (`bronze_seed_silver_gold`,
`load_history`, `daily_incremental`, `bootstrap_full`, `full_reconcile`)?

Specifically, research and answer against AWS's primary documentation
(Step Functions API reference / developer guide), not memory:

1. **Execution status eligibility.** `RedriveExecution` is documented for
   FAILED, ABORTED, and TIMED_OUT executions — does an operator-initiated
   `StopExecution` produce an ABORTED status that qualifies, or does it
   need a different stop mechanism to be redrivable?
2. **Retention/redrive window.** How long after an execution starts (or
   stops) can it still be redriven? Is this fixed or configurable?
3. **STANDARD vs EXPRESS.** Confirm this platform's state machines are all
   STANDARD workflow type (check `infra/scripts/deploy-aws-application.sh`'s
   `create-state-machine`/`update-state-machine` calls for a `type` param —
   default is STANDARD if unspecified, but verify) and that redrive is
   actually restricted to STANDARD as commonly stated.
4. **Distributed Map semantics.** This platform's `BatchSilver`/
   `Stage1Parallel` stages are Distributed Map states (`ItemProcessor`).
   When a Distributed Map's parent execution is redriven, does it re-run
   only the failed/incomplete child Map Run items, or does it restart the
   whole Map from scratch? Is there a separate, more granular Map Run
   redrive API distinct from execution-level redrive?
5. **Definition-drift tolerance.** This repo redeploys ASL state machine
   definitions on every `deploy-aws-application.sh` run (new task-def
   digests get baked into `RunTask` parameters). If a state machine's
   definition is updated *after* an execution starts but *before* that
   execution is redriven, does `RedriveExecution` still work, and if so,
   does it redrive against the old (execution-start-time) definition or
   the new one? This directly matters here: the actual incident that
   prompted this map (2026-08-08) involved deploying a new MDM image/task
   revision specifically *because* the running execution needed to be
   stopped and fixed — the redrive question needs to account for "the
   reason we stopped it was to change the definition," not just "it
   crashed and we want the exact same thing to retry."
6. **Redrive count limits.** Is there a cap on how many times a single
   execution can be redriven?
7. **Cost/complexity of the alternative.** As a comparison baseline, note
   what a custom checkpoint/resume-input pattern would require (e.g. a
   `resume_from_stage` input field threaded through Choice states, similar
   to the existing `release_mode` gate) — rough shape only, not a full
   design; that's for a follow-up decision ticket if redrive doesn't fit.

Report a clear per-question answer with citations, plus an overall verdict:
does native redrive cover this platform's actual failure/stop pattern, or
does the definition-drift or Distributed Map gap rule it out for the
stages that matter most (BatchSilver, MdmRun)?

## Answer

### Repo facts first (confirmed by reading `infra/scripts/deploy-aws-application.sh`)

- **All five pipelines are STANDARD.** `upsert_state_machine()` — the single helper every
  `write_*_definition` call in this file routes through — calls `create-state-machine`
  with an explicit `--type STANDARD` (`infra/scripts/deploy-aws-application.sh:4258`).
  `update-state-machine` (the redeploy path, `:4265`) has no `--type` flag at all — AWS
  doesn't let you change a state machine's type after creation, so every subsequent
  `deploy-aws-application.sh` run stays STANDARD too. There is no EXPRESS state machine
  anywhere in this repo's Step Functions surface.
- **Every Distributed Map's child `ExecutionType` is STANDARD, not EXPRESS.** Grepping
  `ItemProcessor`/`DISTRIBUTED` turns up the Map states this ticket asks about —
  `BatchSilver` (`:3643-3663`, `silver_mdm_gold`'s reprocessing Map), `Stage1Parallel`'s
  `WindowedBootstrap` (`:2384-2438`, `load_history`), `Stage0CompanyIdentity`
  (`:2298-2338`), `StrictBatchSilver` (`:3901-3925`), and `BuildPartitions`
  (`:4167-4178`, `generation_build`) — and every one of them sets
  `"ProcessorConfig": {"Mode": "DISTRIBUTED", "ExecutionType": "STANDARD"}`.
- **`BatchSilver` itself:** `Type: Map`, `MaxConcurrency: int(batch_concurrency)`,
  `ToleratedFailurePercentage: 0`, reads `cik_batches.jsonl` via `ItemReader`, runs
  `bootstrap-batch --artifact-policy skip --parser-policy skip` per batch, then
  `Next: "MdmRun"` (`:3643-3663`).
- **`MdmRun` is a plain sequential ECS `Task` state, not a Map** — one `ecs_state(...)`
  call (`mdm run --entity-type all`) chained `MdmRun → MdmBackfill → MdmExport →
  MdmSync → MdmVerify → GoldRefresh` (`:3669-3678`). This matters directly for Q4/verdict:
  none of the Distributed-Map-specific redrive granularity applies to it.

### Q1 — Execution status eligibility

`StopExecution` produces `ABORTED`. `DescribeExecution`'s response schema documents the
full status enum as `RUNNING | SUCCEEDED | FAILED | TIMED_OUT | ABORTED |
PENDING_REDRIVE` ([API_DescribeExecution](https://docs.aws.amazon.com/step-functions/latest/apireference/API_DescribeExecution.html)),
and `RedriveExecution`'s own eligibility rule is simply **"The execution status isn't
`SUCCEEDED`"** ([API_RedriveExecution](https://docs.aws.amazon.com/step-functions/latest/apireference/API_RedriveExecution.html)),
with the developer guide spelling out the same three terminal-failure statuses
explicitly: *"You can use redrive to restart executions of Standard Workflows that
didn't complete successfully in the last 14 days. These include failed, aborted, or
timed out executions."* ([Restarting state machine executions with redrive](https://docs.aws.amazon.com/step-functions/latest/dg/redrive-executions.html)).
So: **yes, an operator-initiated `StopExecution` produces exactly the `ABORTED` status
that qualifies — no different stop mechanism is needed.**

### Q2 — Retention/redrive window

**Fixed, not configurable: 14 days.** Per the service quotas table: *"Execution
redrivable period | 14 days | Hard quota applies to Distributed Map state. Redrivable
period refers to the time during which you can redrive a given Standard Workflow
execution. **This period starts from the day a state machine completes its
execution**"* ([Step Functions service quotas](https://docs.aws.amazon.com/step-functions/latest/dg/service-quotas.html))
— i.e. the clock starts at stop/completion time, not execution-start time. Two more
hard gates stack on top of the 14 days: the 1-year max-open-time ceiling, and an
execution event-history count that must stay under 24,999 (each redrive appends an
`ExecutionRedriven` event, so repeated redrives eat into this budget) — both listed on
the same `RedriveExecution` eligibility list cited in Q1.

### Q3 — STANDARD vs EXPRESS

Confirmed both halves. This platform's state machines are STANDARD (repo facts above),
and AWS restricts `RedriveExecution` to STANDARD outright: *"This API action is not
supported by `EXPRESS` state machines"* ([API_RedriveExecution](https://docs.aws.amazon.com/step-functions/latest/apireference/API_RedriveExecution.html)).
Distributed Map itself carries the same restriction one level down — *"Distributed mode
is supported in Standard workflows but not supported in Express workflows"*
([Using Map state in Distributed mode](https://docs.aws.amazon.com/step-functions/latest/dg/state-map-distributed.html))
— so this repo's STANDARD-everywhere choice is a precondition already satisfied for any
of Q4-Q7 to be relevant at all, not something that needs fixing.

### Q4 — Distributed Map semantics

Two distinct facts, both favorable in isolation:

1. **No separate Map-Run-scoped redrive API — it's driven through the parent
   execution's `RedriveExecution` call.** *"To redrive a workflow that includes a
   Distributed Map state whose Map Run failed, you must redrive the parent workflow.
   The parent workflow redrives all the unsuccessful states, including a failed Map
   Run."* ([Redriving Map Runs](https://docs.aws.amazon.com/step-functions/latest/dg/redrive-map-run.html)).
   `DescribeMapRun`/`redriveStatus` lets you inspect eligibility per Map Run, but the
   actual redrive call target is always the parent execution ARN.
2. **Granularity is per-child-execution, not whole-Map-from-scratch** — for STANDARD
   child executions (which is what this repo uses everywhere, per Q3): *"All child
   workflow executions that failed, timed out, or canceled in the original execution
   attempt are redriven using the RedriveExecution API action. These child workflows
   are redriven from the last state in ItemProcessor that resulted in their
   unsuccessful execution."* ([Redriving Map Runs — Child workflow execution redrive
   behavior](https://docs.aws.amazon.com/step-functions/latest/dg/redrive-map-run.html)).
   Successfully-completed children are not rerun. Concretely for `BatchSilver`: if 400
   of 680 `cik_batches.jsonl` batches had already succeeded when the parent was
   stopped, a redrive would resume only the ~280 that were failed/timed-out/canceled
   at stop time — a real, meaningful improvement over `load_history`'s full
   Stage-0 restart.

Caveats: a hard cap of 1000 redrives per Map Run applies (Q6), and individual STANDARD
child executions are still separately gated by their own 14-day/25,000-event
eligibility — *"A Standard child workflow execution might not be redrivable if the
parent workflow execution has closed within 14 days, but the child workflow execution
closed earlier than 14 days"* (same page).

### Q5 — Definition-drift tolerance (the decisive constraint)

**Redrive uses the definition frozen at the original execution's start time — never the
current/latest one.** Two independent, directly on-point primary-source statements:

- `RedriveExecution` API reference: *"Redriven executions use the same state machine
  definition and execution ARN as the original execution attempt."* ([API_RedriveExecution](https://docs.aws.amazon.com/step-functions/latest/apireference/API_RedriveExecution.html))
- Developer guide, stated as a direct consequence: *"Redriven executions use the same
  state machine definition and execution ARN that was used for the original execution
  attempt... Even if you update your alias to point to a different version, the
  redriven execution continues to use the version associated with the original
  execution attempt. **Because redriven executions use the same state machine
  definition, you must start a new execution if you update your state machine
  definition.**"* ([Restarting state machine executions with redrive](https://docs.aws.amazon.com/step-functions/latest/dg/redrive-executions.html))
- `UpdateStateMachine` API reference confirms the other side of the same fact — a
  redeploy doesn't even touch what a stopped execution would resume against:
  *"Running executions will continue to use the previous `definition` and
  `roleArn`."* ([API_UpdateStateMachine](https://docs.aws.amazon.com/step-functions/latest/apireference/API_UpdateStateMachine.html))

Applied to this repo: `upsert_state_machine()` calls `update-state-machine` on every
`deploy-aws-application.sh` run, baking a new ECS task-definition ARN/digest into every
`RunTask` parameter in the ASL (that's the mechanism by which a new MDM image lands in
the pipeline). **RedriveExecution cannot pick up that new definition under any
circumstance.** For the actual 2026-08-08 incident pattern this ticket is about — stop
specifically *because* a new task-def/image needs to ship — redrive would resume the
*old*, pre-fix ASL (old task-definition ARN), i.e. it would just re-trigger the same bug
that motivated the stop. A fresh `StartExecution` against the newly-updated state
machine is the only way to get the new definition applied; `RedriveExecution` and
"stop-to-deploy-a-fix" are mutually exclusive tools for the same stop event.

### Q6 — Redrive count limits

Two different scopes, two different answers:

- **Map Run redrive: a documented hard cap of 1000.** Service quotas table: *"Maximum
  redrives of a Map Run | 1000 | This quota applies to Distributed Map state | Hard
  quota"* ([Step Functions service quotas](https://docs.aws.amazon.com/step-functions/latest/dg/service-quotas.html)),
  reiterated as an eligibility condition: *"You haven't exceeded the hard limit of 1000
  redrives of a given Map Run. If you've exceeded this limit, you'll receive the
  `States.Runtime` error."* ([Redriving Map Runs](https://docs.aws.amazon.com/step-functions/latest/dg/redrive-map-run.html))
- **Plain top-level (non-Map) STANDARD execution redrive: no documented numeric cap.**
  `DescribeExecution`'s `redriveCount` field just counts attempts with no stated
  ceiling of its own ([API_DescribeExecution](https://docs.aws.amazon.com/step-functions/latest/apireference/API_DescribeExecution.html)).
  The only binding limits are the shared eligibility gates from Q2 — the 14-day
  redrivable window and the <24,999 event-history ceiling every redrive eats into via
  its own `ExecutionRedriven` event.

### Q7 — Cost/complexity of the checkpoint/resume-input alternative (rough shape only)

This repo already has the load-bearing precedent this pattern would extend: `Choice`
states gating on execution-input fields (`release_mode`, `artifact_policy`,
`tracking_status_filter` per the grep evidence above and elsewhere in this file's
CLAUDE.md Phased Pipeline section). A `resume_from_stage` field would need, at minimum:

1. A new execution-input field threaded through every top-level pipeline's `StartAt`
   region, read by a new leading `Choice` state.
2. One `Choice` branch per stage boundary (`Stage0`/`Stage1`/`Stage1B`/`MdmRun`/
   `GoldRefresh`) that skips straight to the requested stage instead of re-entering
   `StartAt`.
3. A way to reconstruct the intermediate manifests each stage depends on
   (`cik_windows.jsonl`, `cik_batches.jsonl`) without re-running the `Seed*` states that
   normally produce them fresh per run-id — those are written keyed by
   `$$.Execution.Name`, so a resumed run would need to either reuse the original
   run-id's manifest or regenerate an equivalent one.
4. Idempotent re-entry at the chosen stage. This is plausible without redoing SEC
   fetches — silver/MDM steps already lean on bronze-cache idempotency (see this repo's
   own "Artifact-throttle" and "SEC data idempotency" conventions) — but it's a new
   invariant to prove for each stage's resume entry point, not something that falls out
   for free.

This is a genuinely custom mechanism to design, build, and test — not a superficial
flag flip — and is explicitly out of scope for this ticket (flagged in the ticket text
itself as a follow-up decision ticket).

## Overall verdict

**Native `RedriveExecution` is a real, well-documented improvement for one failure
class — plain infra-flake stops where no code/task-def change is needed — but it does
not cover this platform's actual recurring stop pattern, and the gap is structural, not
an edge case.**

- **Where it genuinely helps:** a `BatchSilver`/`Stage1Parallel` Map Run that fails or
  times out from a transient cause (a flaky ECS task, throttling, a Postgres blip) with
  no fix required — redrive resumes only the failed/canceled batches, not all 680, and
  does so through a documented, supported API rather than a bespoke restart. This is a
  meaningful win over "restart `load_history` from Stage 0."
- **Where it falls short, decisively (Q5):** the platform's actual 2026-08-08 trigger —
  stopping an execution *specifically to ship a fix* — is exactly the scenario
  `RedriveExecution` cannot serve. Redrive is contractually pinned to the
  execution-start-time definition; the entire point of stopping to deploy was to change
  that definition, and redrive would silently resume the stale, pre-fix ASL. There is no
  way to "redrive against the new definition" — AWS's own docs say to start a new
  execution instead, which is the exact "full restart" this ticket was trying to avoid.
- **`MdmRun` specifically:** it's a plain sequential `Task` state, not a Map, so none of
  Q4's per-child-execution granularity applies to it at all — a Task-state redrive just
  reschedules and reruns the whole task (with its retry-attempt counter and
  `TimeoutSeconds` reset to 0, per the [redrive behavior table](https://docs.aws.amazon.com/step-functions/latest/dg/redrive-executions.html)),
  which is no more granular than a fresh restart of that one step would be. Redrive's
  distinctive value in this platform is concentrated entirely in the Distributed Map
  stages (`BatchSilver`, `Stage1Parallel`, `Stage0CompanyIdentity`, `BuildPartitions`),
  not in `MdmRun`/`MdmBackfill`/`MdmExport`/`MdmSync`/`MdmVerify`/`GoldRefresh`.

**Recommendation for the follow-up decision ticket:** adopt `RedriveExecution` as a
secondary fast-path specifically for pure-retry stops/failures where the state machine
definition is not changing, but do not treat it as a substitute for a checkpoint/
resume-input mechanism (Q7) — that mechanism is still required to preserve progress
across the "stop to deploy a fix" pattern that actually motivated this ticket, since
that is the one case native redrive is structurally unable to serve.
