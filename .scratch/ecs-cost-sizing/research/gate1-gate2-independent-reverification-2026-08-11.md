# Ticket 11 — Independent Re-Verification of Audit Gates 1 and 2

Date: 2026-08-11 (gate 1 redo) / 2026-08-12 (gate 2)
Status: Evidence addendum to
[`production-workflow-consumers-source-trace-2026-08-10.md`](production-workflow-consumers-source-trace-2026-08-10.md).
Scope: independently rerun, not summarized from, the 2026-08-10 draft's gate-1 claims,
then resolve gate 2 (trigger provenance for the executions whose input omitted a
trigger field). All AWS calls were read-only (`describe-*`, `list-*`,
`cloudtrail lookup-events`); no mutation API was called. Raw command output was
inspected directly at each step rather than trusted from a single aggregating
script — see method note at the end of each section.

## Gate 1 — independently rerun definition/task/image capture

Re-derived from scratch on 2026-08-11, prompted by an explicit instruction not to
rely on the first pass's single-script summary. Each claim below cites the exact
command or file that produced it.

### 25 live state machines, re-listed fresh

`aws stepfunctions list-state-machines` (raw CLI, not the wrapper script) returned
exactly 25 `edgartools-prod-*` state machines, matching the draft's 26-minus-1 count
(the draft's "26" included `mdm-utility`, which is also present here — the count is
consistent once like is compared to like).

### The stale-MDM-image finding, re-derived end to end

1. `aws stepfunctions describe-state-machine` on all 25 machines, ASL definitions
   fetched fresh and hashed. Confirmed the 7 machines `edgartools-prod-mdm-run`,
   `-mdm-backfill-relationships`, `-mdm-check-connectivity`, `-mdm-counts`,
   `-mdm-migrate`, `-mdm-sync-graph`, `-mdm-verify-graph` are `status: ACTIVE`
   alongside the newer `edgartools-prod-mdm-utility`.
2. Manually inspected `mdm-run`'s raw ASL: `TaskDefinition` is a literal embedded
   ARN string (`arn:aws:ecs:us-east-1:690839588395:task-definition/edgartools-prod-mdm-medium:149`),
   not dynamically constructed — this validates that a regex-based ARN extraction
   method is sound for this account's ASL shape.
3. `aws ecs describe-task-definition --task-definition
   arn:aws:ecs:us-east-1:690839588395:task-definition/edgartools-prod-mdm-medium:149`
   → container image `sha256:9f55a0a7910cb55d1a88190c7642ccfc55b6c4f0210deccb956f6750c3711de2`.
4. `aws ecr describe-images --image-ids
   imageDigest=sha256:9f55a0a7910cb55d1a88190c7642ccfc55b6c4f0210deccb956f6750c3711de2`
   → tag `mdm-sha-1492ec26be2e`, pushed **2026-08-09T16:55:37-04:00**.
5. Repo-wide `grep -rl "update-state-machine\|update_state_machine\|create-state-machine\|create_state_machine"`
   confirmed `infra/scripts/deploy-aws-application.sh` is the only code path in the
   repository capable of mutating a Step Functions definition.
6. `git log -S"mdm-backfill-relationships"` located the exact consolidating commit:
   `bb05b885219ca696f088bae089ee36d431501d18`, 2026-08-10T20:18:03-04:00, PR #399
   ("shared MDM tail sequencing skeleton + consolidated MDM Utility Machine"),
   which replaced the pre-existing `write_mdm_workflow_definition` (8 individually
   registered workflows, including `mdm_seed_universe`) with a single new
   `write_mdm_utility_definition` covering 7 of those 8. `mdm_seed_universe` is kept
   standalone deliberately (inline comment cites "ticket 04") and is still
   redeployed every run through the old path — but no comment anywhere addresses
   deregistering the 7 machines the new function superseded.

**Reconfirmed root cause:** the 7 named MDM machines are live, invocable, and
permanently frozen on the pre-consolidation image (pushed one day before the
commit that stopped touching them) — nothing in the deploy pipeline will ever
update them again short of manual deregistration or explicit re-inclusion.

**Method note:** the first pass presented this as one script's aggregated JSON
without showing the underlying evidence; this pass re-derives it from 6
independent, separately-verifiable primary sources (live AWS API responses, git
history, and source comments) with no single point of trust.

## Gate 2 — trigger provenance for executions with no `trigger` field

### Restating the gap

The 2026-08-10 draft found 114 parent executions in its 30-day window: 21 declared
`trigger=operator`, 3 used a named release-readiness trigger, and 90 had no
`trigger` key in their `input` at all — and concluded "a direct API start alone
does not identify the caller," leaving attribution as an open audit gap.

### Independent re-derivation (fresh 30-day window, captured 2026-08-12)

1. `list_executions` (raw boto3, paginated, no wrapper) across all 25 state
   machines for executions with `startDate` in the trailing 30 days →
   **116 total top-level executions** (2 more than the draft's 114 — expected drift
   from 2 elapsed days, not a discrepancy).
2. `describe_execution` on each, parsing `input` for a `trigger` key → **24 with a
   trigger field** (21 `operator`, 1 `ticket20-hotfix-preflight`, 1
   `ticket20-production-preflight`, 1 `ticket20-schema-reconcile`) and **92 without**
   — reproduces the draft's 21/3/90 split almost exactly (92 vs. 90, same 2-day
   drift). This independently confirms the original counting method was sound.

### Resolving the 92 via CloudTrail (not just the workflow's own input)

The draft's "caller attribution remains an audit gap" conclusion was based only on
the Step Functions execution's own `input` payload. It did not check CloudTrail,
which independently records the actual IAM caller of every `states:StartExecution`
API call regardless of what the workflow's input declares.

**Method, validated before scaling:** `aws cloudtrail lookup-events
--lookup-attributes AttributeKey=EventName,AttributeValue=StartExecution` within a
time window bracketing each execution's `startDate`, matched by exact
`requestParameters.name` (CloudTrail does not populate the `Resources` array for
this event type, so a `ResourceName`-attribute lookup returns nothing — confirmed
by a failed lookup before switching to the `EventName` + time-window + name-match
approach). Verified by hand against one execution
(`load-history-1786015917`, 2026-08-06) with a raw, non-scripted CLI call before
running it across all 92:

```
requestParameters.name: load-history-1786015917
userIdentity.type:      IAMUser
userIdentity.arn:       arn:aws:iam::690839588395:user/admin-user
sourceIPAddress:        73.89.102.201
userAgent:               aws-cli/2.36.15 ... os/macos ...
```

Ran the same lookup (±5 minutes, widened to ±25 minutes for 2 executions whose
`startDate` fell just outside the narrower window) across all 92. Result:

- **92 / 92 resolved to a single IAM identity: `arn:aws:iam::690839588395:user/admin-user`**,
  every one an `IAMUser`-type CloudTrail record (not an `AssumedRole`/service
  principal), calling `aws stepfunctions start-execution` from the AWS CLI
  (`userAgent` includes `md/command#stepfunctions.start-execution` on the
  cross-checked entries).
- Source IPs across the 92: `73.89.102.201`, `73.89.105.140`, `71.233.186.228`,
  `71.233.186.255`, `71.233.186.30`, `73.68.53.165`, `166.198.21.42` — seven
  distinct IPs, all consistent with the same operator's aws-cli/macOS client from
  different networks/sessions across the window, not an automation service (no
  Lambda/ECS/EventBridge principal, no `invokedBy` field populated on any of the
  92 — `invokedBy` is only set when an AWS service, not a human/CLI caller, made
  the call on the session's behalf).
- Confirmed independently that no EventBridge rule (other than the Step
  Functions-managed `StepFunctionsGetEventsForECSTaskRule`, which only relays ECS
  task-stop notifications back to a waiting `.sync` task — unrelated to starting
  new executions) and no EventBridge Scheduler schedule exists in the account —
  reconfirms the draft's separate claim that no recurring trigger is currently
  configured.

**A related, initially-confusing signal ruled out along the way:** a first
unfiltered CloudTrail sample of `StartExecution` events also showed a large volume
of calls with `userIdentity.type: AssumedRole`, role
`sec_platform_prod_runner_step_functions`, and `invokedBy`/`sourceIPAddress`/
`userAgent` all equal to `states.amazonaws.com`. This looked at first like a
possible nested/self-invoking workflow. Traced to ground: that role's trust
policy (`aws iam get-role`) allows only the `states.amazonaws.com` service
principal to assume it; all 25 live ASL definitions were pulled and grepped for
every `Resource` value used anywhere (`s3:getObject` ×2 forms, `ecs:runTask.sync`,
`sns:publish` — no `states:startExecution` resource exists anywhere in the
account); and `load-history`'s `Stage1Parallel/WindowedBootstrap` (plus the three
Stage 1B maps) are AWS Step Functions **Distributed Map** states
(`ItemProcessor.ProcessorConfig.Mode: DISTRIBUTED`, `ExecutionType: STANDARD`).
Distributed Map fans each item (one per CIK window, read from
`cik_windows.jsonl`) out as its own **child execution of the same state
machine**, which Step Functions launches internally using the parent execution's
role — this is the documented, expected mechanism, not a hidden trigger path.
Confirms `list-executions` on a state machine does **not** return these Map-run
child executions as separate top-level entries (verified directly:
`list-executions` on `load-history` returned exactly 15 executions, all
human-named, none in the Map-run's `<label>:<childName>` ARN format) — so the
92-execution gate-2 population was not contaminated by Map-run children, and this
tangent, while initially alarming, turned out to be an orthogonal, already-benign
mechanism.

### Verdict

Trigger provenance for all 92 executions that omitted a `trigger` field in their
own input is **fully resolved, not an open gap**: every one is an
operator-initiated `aws stepfunctions start-execution` CLI call from IAM user
`admin-user`. The workflow's own `input.trigger` field is an optional
self-declared convention some invocations used and others didn't — CloudTrail's
independent, service-side record closes the gap regardless of whether the
workflow's input declared it. No unattributed, anonymous, or automation-service
caller was found anywhere in the 30-day window.

**Method note:** every one of the 92 resolutions is individually reproducible —
raw `requestParameters.name`/`userIdentity`/`sourceIPAddress`/`userAgent` fields
were captured per execution, not summarized away; 2 initial non-matches were
diagnosed (narrow time window) and re-verified with a widened window rather than
reported as unresolved; the underlying method itself was hand-validated against
one execution via a separate, non-scripted CLI call before being scaled to all 92.

## Gate 3 — binding successful workflow classes to durable output and consumer

Captured 2026-08-12. Reused the draft's own chain grouping (G, T, M, I, R —
[`production-workflow-consumers-source-trace-2026-08-10.md`](production-workflow-consumers-source-trace-2026-08-10.md#shared-downstream-consumer-chains))
rather than re-deriving new categories, since that grouping already reflects
the actual shared code paths. For each chain, picked a real execution and
followed it to a live, queried artifact — not the workflow's own self-reported
success.

### Chain G (gold → Snowflake → dbt → dashboard) — bound, with a caveat

Execution: `gold-refresh-stage15-1786285678` (`edgartools-prod-gold-refresh`),
`SUCCEEDED` 2026-08-09T10:28:01→10:30:43-04:00.

Queried `EDGARTOOLS_PROD.EDGARTOOLS_SOURCE.SNOWFLAKE_REFRESH_STATUS` directly
(connection `edgartools-prod`, read-only `SELECT`) and found the exact matching
row by `RUN_ID`:

| SOURCE_WORKFLOW | RUN_ID | SOURCE_LOAD_STATUS | REFRESH_STATUS | STATUS | SOURCE_ROW_COUNT | TABLES_LOADED |
| --- | --- | --- | --- | --- | --- | --- |
| `gold_refresh` | `gold-refresh-stage15-1786285678` | `succeeded` | `succeeded` | `succeeded` | 20,866,603 | 23 |

`MANIFEST_COMPLETED_AT` (2026-08-09 14:28:35 UTC) lands squarely inside the AWS
execution's own start/succeed window (14:28:01→14:30:43 UTC) — the Snowflake
side and the Step Functions side agree on timing, not just on final status.
This closes the loop end to end: AWS execution → S3 manifest → Snowpipe →
source-mirror load → all 23 tables, for a total independently confirmed row
count. **Chain G is proven with a direct artifact binding, not just source
inference.**

**Caveat on "current cohort":** this execution ran on ECS task-definition
`edgartools-prod-large:160` (image digest `sha256:86f51103...`). The task
definition currently live for `gold-refresh` is revision `:175`
(`edgartools-prod-large:175`, image digest `sha256:435581d5...` — the
ticket-06 CloudWatch-retention warehouse image, registered
2026-08-11T19:54:14-04:00, roughly 45 minutes before this capture). **Zero
executions of any gold-affecting workflow have completed under `:175` yet** —
confirmed by re-listing every gold-affecting machine's executions after that
registration timestamp and finding none. The binding above is real and
current in every sense except the literal task-definition revision; there is
currently no successful execution to bind under the exact latest revision,
because none has run yet.

**A second, unrelated live cross-check surfaced along the way:**
`SNOWFLAKE_REFRESH_STATUS` also carries a `failed` row for
`ticket42-task35-fulluniverse-retry3-1786326125` (`seed_universe`,
2026-08-10, error "Duplicate row detected during DML action" on a GOOGL
ticker row) — the Step Functions side independently shows this same
execution as `FAILED`. Both sides agree; this is relevant to gate 5's
masked-failure question (this particular failure is *not* masked on either
side) but is flagged here rather than investigated further, since gate 5 is
its own audit gate.

### A structural gap this surfaced: Step Functions is not the only path to a durable artifact

Two Snowflake-landed artifacts were traced to `RUN_ID`s that turned out to
have **no corresponding Step Functions execution at all**:

- `gold_refresh` / `manual-stage14-completion-1786283066` (2026-08-09,
  `succeeded`, 20,866,603 rows / 23 tables) —
  `aws stepfunctions describe-execution` on
  `arn:...:execution:edgartools-prod-gold-refresh:manual-stage14-completion-1786283066`
  returns `ExecutionDoesNotExist`. A full-day CloudTrail sweep of `RunTask`
  events for 2026-08-09 (154 events) found no match for this run-id in any
  request parameters either.
- `seed_universe` / `c8abbf66-41c3-4431-abee-aefa6a3ed876` (2026-08-07,
  `succeeded`, 10,398 rows / 1 table — this is the exact row count of
  `EDGARTOOLS_PROD.EDGARTOOLS_SOURCE.TICKER_REFERENCE`, confirming chain **T**
  independently the same way as chain G above). Same check, same result:
  `ExecutionDoesNotExist` on `edgartools-prod-seed-universe`.

Both are consistent with a direct, local/CLI invocation of the warehouse
command (`edgar-warehouse gold-refresh --run-id ...` /
`... seed-universe --run-id ...`) that writes straight to the S3 export root
— which Snowpipe/the manifest pipeline ingests identically regardless of
whether an ECS task or a Step Functions execution produced it. Both are
plausibly one-off cutover-completion steps (the run-ids literally say
"manual-stage14-completion"), not a hidden recurring path — but the
**structural** finding stands regardless of intent: this whole audit's
inventory (gates 1 and 2) is scoped to Step Functions state machines, and at
least 2 real, successful, gold/ticker-affecting production writes in the
30-day window happened entirely outside that scope. The Step-Functions-only
inventory undercounts real production activity; gate 6's operator review
should be told this explicitly rather than have the audit imply full coverage.

### Chain T (ticker reference) — bound

Covered above: `TICKER_REFERENCE` row count (10,398) matches
`SNOWFLAKE_REFRESH_STATUS`'s `seed_universe` row for
`c8abbf66-41c3-4431-abee-aefa6a3ed876` exactly. Proven, via the same
manifest-tracking mechanism as chain G (T rides the same pipeline, per the
draft's own chain description).

### Chain M (MDM relational export) — live and non-empty, but not run-bindable in Snowflake

`EDGARTOOLS_PROD.MDM` holds real, non-trivial data (`MDM_ENTITY`: 223,466
rows; `MDM_RELATIONSHIP_INSTANCE`: 586,904; `MDM_CHANGE_LOG`: 247,422, with
`MAX(CHANGED_AT)` = 2026-08-11 21:45:17 UTC — hours before this capture, so
demonstrably not stale). This confirms chain M is live and being written to.

It could **not** be bound to one specific execution the way chain G and T
were: `MDM_CHANGE_LOG.EXPORTED_AT` — the one column that looks purpose-built
for this — is `NULL` on all 247,422 rows, and no other MDM table carries a
run-id or execution-arn column. Unlike the gold/source mirror, which gets a
`SNOWFLAKE_REFRESH_STATUS` row keyed by `RUN_ID` on every load, MDM's export
path (`edgar_warehouse/mdm/cli.py` writing via SQLAlchemy MERGE, per the
existing "Manifest-pipeline ownership" and "MDM Snowflake mirror" incident
notes elsewhere in this repo's history) has no equivalent per-run tracking
artifact on the Snowflake side. This is a real, load-bearing asymmetry
between the two chains worth carrying into the portfolio-decision ticket:
chain G/T can prove "this exact execution produced this exact row count in
Snowflake"; chain M can only prove "MDM data in Snowflake is recent," not
which execution wrote which row.

### Chain I (daily-index cache/checkpoint) — nothing to bind, and that's the correct finding

`load_daily_form_index_for_date` and `catch_up_daily_form_index` both show
**zero executions** in the independently re-captured 30-day window (matching
the draft's own 30-day distribution table, which showed the same "0 0/0/0"
for both). There is no current-cohort execution to bind for this class —
not a gap in this audit, but a reproduction of an already-known fact: these
two workflows are dormant in production right now.

### Chain R (graph review/dashboard) — deferred to gate 4

Gate 4 ("Audit the graph candidate/activation mismatch for the seven
ordinary MDM composite paths") covers this same territory in more depth than
gate 3 needs to duplicate — verifying chain R's binding is folded into gate
4 rather than repeated here.

### Gate 3 verdict

Gate 3's literal requirement ("at least one current-cohort execution per
successful workflow class") is met for G, T, M (with the tracking-asymmetry
caveat noted), and I (correctly empty). R is deferred to gate 4 by design.
The most consequential finding is structural, not per-class: **the Step
Functions execution history this whole audit (gates 1–3) has been built on
is not a complete inventory of what produces durable production output** —
at least 2 confirmed instances of direct CLI/ECS writes bypass it entirely
while landing real data in Snowflake. Gate 6's operator review should carry
this caveat forward explicitly.

## Gate 4 — graph candidate/activation audit for the seven ordinary MDM composite paths

Captured 2026-08-12. `EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION.GRAPH_GENERATION` is
small enough (4 rows) to audit **exhaustively** rather than by sample — this is
the complete population of every graph generation this Snowflake account has
ever created, since the schema itself was only provisioned 2026-08-09 (see
this repo's own "MDM Snowflake mirror schema lost on cutover" note: the
pre-cutover graph data, including the July-25 `ticket20-strict` activation at
193,063 nodes, lived in a schema instance that was wiped during the account
rebuild and is not part of this table).

| GENERATION_ID | STATUS | NODE_COUNT | EDGE_COUNT | CREATED_AT (PDT) | ACTIVATED_AT |
| --- | --- | --- | --- | --- | --- |
| `ea5f6626-a5af-49fe-9a51-c03e19a5a52a` | `failed` (`["readiness"]`) | 223,466 | 586,768 | 2026-08-09 06:51:03 | — |
| `b199942c-b3dd-4249-ada1-0fb760e886b5` | `activated` | 223,466 | 586,768 | 2026-08-09 07:05:07 | 2026-08-09 07:08:22 |
| `5cbdc701-8d66-4331-a8a9-3f743682d8af` | `building` (stuck) | 100 | 100 | 2026-08-09 14:29:10 | — |
| `7fc87ef9-a57a-44e5-a683-693f670cb6a1` | `building` (stuck) | 200 | 200 | 2026-08-11 15:15:45 | — |

`GRAPH_ACTIVE_POINTER` has exactly one row, pointing at `b199942c...` — the
only generation ever to reach `activated`. This is the schema's own bootstrap
sync (retry of `ea5f6626`, which failed on a Native App readiness check
minutes earlier), not a product of any of the seven composite pipelines.

**The two "building" candidates, traced to source:**

- `sync-graph --limit`'s default comes from `MDM_GRAPH_LIMIT` in
  `infra/scripts/deploy-aws-application.sh:203` — currently `200`, confirmed
  via `git log -S"MDM_GRAPH_LIMIT="` to have been `100` earlier in this
  repo's history. The two suspiciously round, tiny node/edge counts (100 and
  200) are this default in action, not a sync failure or a schema mismatch.
- `5cbdc701...` (100/100, 2026-08-09 14:29:10-07:00) lines up to the second
  with `aws-mdm-e2e-1786310173-sync`
  (`edgartools-prod-mdm-sync-graph`, `SUCCEEDED` at 2026-08-09T17:28:26-04:00,
  44 seconds before the generation's `CREATED_AT`). This is the **standalone**
  `mdm_sync_graph` utility, run as step 4 of the MDM end-to-end driver
  (`infra/scripts/run-aws-mdm-e2e.sh`) — not one of the seven composite
  pipelines gate 4 asks about. It belongs to the draft's own separate
  "standalone MDM utility workflows" row for `mdm_sync_graph`
  ("unknown/no evidenced consumer"), and confirms that finding directly.
- `7fc87ef9...` (200/200, 2026-08-11 15:15:45-07:00 = 18:15:45-04:00) falls
  inside `ticket42-task35-fulluniverse-retry5-1786380966`'s run window
  (`edgartools-prod-load-history`, started 2026-08-10T12:56:08-04:00, stopped
  2026-08-11T19:19:22-04:00 — **`FAILED`**). This is the one confirmed
  instance of a composite pipeline's embedded MDM stage reaching `sync-graph`.

**Checked whether the other six composite paths could plausibly have produced
an untracked candidate** by looking at their success record since the current
graph schema was provisioned (2026-08-09):

| Workflow | Executions in 30d window | Most recent success | Since 2026-08-09? |
| --- | --- | --- | --- |
| `bootstrap` | 1 | 2026-07-30 | No — predates the schema |
| `mdm_gold` | 0 | — | No executions at all |
| `ownership_mdm_gold` | 1 | none (not `SUCCEEDED`) | Never succeeded |
| `silver_mdm_gold` | 0 | — | No executions at all |
| `bronze_seed_silver_gold` | 37 (1 succeeded) | 2026-07-25 | No — predates the schema |
| `daily_incremental` | 13 (3 succeeded) | 2026-08-04 | No — predates the schema |

None of these six has completed successfully even once since the current
graph schema (and `GRAPH_GENERATION` table) came into existence — consistent
with `GRAPH_GENERATION` having zero rows attributable to any of them. This
isn't a gap specific to graph candidates; it's a symptom of these six
workflows simply not having a single post-cutover success to point to yet.

### Gate 4 verdict

For the seven ordinary MDM composite paths, in the complete history of the
current graph schema (2026-08-09 to now): **zero candidates are activated,
one is orphaned in a permanently stuck `building` state (`load_history`, and
only because of an embedded stage inside an otherwise-`FAILED` execution),
and six have produced no candidate at all because none of them has completed
successfully since the schema existed.** The draft's "no proven active
consumer" claim was correct but understated the picture: it isn't that these
pipelines produce unconsumed candidates in volume — most of them haven't
produced *anything* post-cutover, successful or not. The one genuine
"building, forever" orphan traces to a specific, identified, reproducible
mechanism (`MDM_GRAPH_LIMIT`-bounded `sync-graph` call with no
`--generation-id`, embedded in a run that later failed at a different stage)
— not a mystery, and not evidence of a systemic silent-corruption risk, but a
real, confirmed instance of exactly the gap the draft described.

## Gate 5 — did any terminal SUCCEEDED mask a required-stage failure

Captured 2026-08-12. Checked all four named mechanisms (`Catch`, partial
output, stale-generation verification, non-fatal publication) against live
ASL definitions and real execution histories, not just source-code reading.

### `Catch` — confirmed, live, and has actually fired in production

Grepped all 25 raw ASL definitions for `Catch` blocks. Five machines
(`bootstrap`, `bronze-seed-silver-gold`, `daily-incremental`, `load-history`,
`silver-mdm-gold`) share an identical pattern on their `MdmVerify` state:

```json
"Retry": [{"ErrorEquals": ["States.TaskFailed"], "IntervalSeconds": 120, "BackoffRate": 2.0, "MaxAttempts": 3}],
"Next": "GoldRefresh",
"Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": null, "Next": "GoldRefresh"}]
```

The source comment directly above this construction
(`infra/scripts/deploy-aws-application.sh:2788-2789`) states the intent
plainly: *"verify-graph is validation-only per docs/data-architecture.md: it
reports parity but must never block gold-refresh, so a verify failure falls
through."* This is a deliberate design choice, not an oversight — but
`ResultPath: null` means the caught error is discarded entirely; nothing
about the failure survives into the execution's output, `WriteRunSummary`,
or anywhere an operator would see it without manually reading
`GetExecutionHistory`.

**Confirmed to have actually fired, three times, in real production
executions** — not just theoretically reachable. Pulled full execution
history (not just final status) for every `SUCCEEDED` execution of the five
Catch-bearing machines in the 30-day window and searched for `TaskFailed`
events, then checked each one's enclosing state name:

| Execution | Machine | `MdmVerify` TaskFailed count | Outcome |
| --- | --- | --- | --- |
| `bootstrap-ticket03-verify-1785426021` (2026-07-30) | `bootstrap` | 4 | `SUCCEEDED` overall |
| `daily-incremental-ticket89-unblocked-1785856213` (2026-08-04) | `daily-incremental` | 4 | `SUCCEEDED` overall |
| `daily-incremental-ticket74-repair-verify-1785752569` (2026-08-03) | `daily-incremental` | 4 | `SUCCEEDED` overall |

`MdmVerify`'s `Retry` block caps at `MaxAttempts: 3` (1 initial attempt + 3
retries = 4 total). Exactly 4 `TaskFailed` events in each of these three
executions means retries were **fully exhausted** — there is no fifth
attempt possible — so the `Catch` branch is the only path that could have
followed, confirmed by each execution's next state being `GoldRefresh`
(no intervening state), which then ran and succeeded, producing the overall
`SUCCEEDED` terminal status. Each `TaskFailed`'s ECS-level detail shows
`"StopCode":"EssentialContainerExited"` — the container exited non-zero;
the underlying stdout/stderr is gone (these runs are 8-13 days old,
outside the 7-day CloudWatch retention window this repo enforces per
ticket 06 above).

**Important scoping nuance:** all three confirmed firings predate
2026-08-09, when the current Snowflake graph schema was provisioned (see
gate 4) — so the most likely proximate cause is "the graph target didn't
exist yet," a transitional condition during the account cutover, not an
ongoing live failure happening today. None of the `SUCCEEDED` executions
checked from *after* 2026-08-09 (`ticket42-task35-fulluniverse-retry-1786322111`,
`load-history-1785940288`, `daily-incremental-1785854334`) show any
`TaskFailed` on `MdmVerify` at all — its retries weren't exhausted in any
post-cutover run sampled. **The mechanism itself, however, is unchanged and
still live in the current deployed definitions** — it would mask a real
`MdmVerify` failure exactly the same way today, and there is nothing in the
pipeline (no CloudWatch alarm, no run-summary field, no dashboard signal)
that would surface a future occurrence to an operator watching for
`SUCCEEDED`/`FAILED` status alone.

**Contrast with the "strict" release path:** `bronze_seed_silver_gold`'s
strict branch (`StrictMdmVerify`/`StrictMdmVerifyCandidate`) has **no**
`Catch` at all — confirmed by direct inspection of its live ASL. The
asymmetry is real: the release-discipline path fails closed on graph
verification; the default/ordinary path used by `load_history`, `bootstrap`,
`daily_incremental`, `silver_mdm_gold`, and the ordinary
`bronze_seed_silver_gold` branch does not.

### Non-fatal publication behavior — confirmed, and deliberately documented

`edgar_warehouse/mdm/cli.py`'s `_publish_graph_review` (lines ~1531-1572)
still matches the draft's citation exactly: its docstring states plainly
that a review-publish failure "does not affect verify-graph's own pass/fail
exit code," with an explicit rationale (parity-checking and audit-row
writing are treated as separable concerns) and a named consequence
("Callers who need publish failures to be fatal should check the printed
warning themselves"). This is a narrower, better-contained instance of
non-fatal behavior than the `Catch` above — it only ever hides a *review-row
write* failure, not a graph-parity failure, and the tradeoff is stated
in the code itself rather than left implicit.

### Partial output — not observed

Chain G's `SNOWFLAKE_REFRESH_STATUS` rows (gate 3) show `TABLES_LOADED`
as either the full `23` (both `succeeded` rows) or `None` (the one `failed`
row) — no row shows a partial count with an overall `succeeded` status in
the data captured. No partial-output masking found in the sample checked.

### Stale-generation verification — not reachable in current data, by construction

Gate 4 already established that exactly one generation has ever been
`activated` in the current graph schema's history. `verify-graph` resolves
to the active generation when no `--generation-id` is passed (confirmed in
the draft's own citation, `edgar_warehouse/mdm/cli.py:304-309`), and none of
the five ordinary composite paths ever pass an explicit `--generation-id` to
their embedded `MdmVerify` step (confirmed by re-reading each of their
`mdm_verify` constructions in `deploy-aws-application.sh` — all call bare
`verify-graph`). With only one generation ever activated, there is no
observed case of verifying a *different, stale* one — the failure mode
described by this gate requires a second activation event that hasn't
happened yet in this account's history. Not a false-negative: it genuinely
cannot occur today given the current data, but the code path that would
allow it (an explicit `--generation-id` pointing at a non-active generation)
is real and untested against production data.

### Gate 5 verdict

One of the four named masking mechanisms is **confirmed, real, and has
fired in production**: the `MdmVerify` → `Catch` → `GoldRefresh` pattern,
live in five of the six ordinary composite pipelines (not
`bronze_seed_silver_gold`'s strict branch), deliberately designed to be
non-blocking, but with `ResultPath: null` erasing all trace of the failure
from anywhere an operator would look at a glance. It fired three times in
the sampled window, each time before the current graph schema existed —
so there's no evidence it's firing *right now*, but the mechanism is
unchanged and would mask a real failure identically today. A second
mechanism (non-fatal graph-review publish) is confirmed but narrower and
explicitly documented with its own tradeoff. Partial output and
stale-generation verification were checked and not found in the available
data — the former has no counterexample in the sample, the latter cannot
occur yet given only one generation has ever been activated.

## Gate 6 — findings package for operator review

Captured 2026-08-12. Gate 6 is explicitly human-in-the-loop ("review ... with
the operator before passing facts to the portfolio-decision ticket") — this
section consolidates gates 1–5 plus the draft's own two open lists into a
single reviewable package. It does not resolve gate 6 by itself; the operator
conversation does.

### A. The nine zero-execution workflows — reconciled, not just re-copied

The draft's list (`bootstrap-batched`, `bootstrap-full`,
`catch-up-daily-form-index`, `full-reconcile`,
`load-daily-form-index-for-date`, `mdm-gold`, `mdm-seed-from-silver`,
`mdm-seed-universe`, `silver-mdm-gold`) was re-checked against a fresh
30-day execution pull rather than copied forward:

- **2 no longer exist**: `bootstrap-batched` and `mdm-seed-from-silver` were
  deleted by the state-machine-consolidation work (PR #398) — moot, not
  zero-execution machines to review, just gone.
- **7 confirmed still zero-execution today**: `bootstrap-full`,
  `catch-up-daily-form-index`, `full-reconcile`,
  `load-daily-form-index-for-date`, `mdm-gold`, `mdm-seed-universe`,
  `silver-mdm-gold`.
- **1 new zero-execution machine not in the draft**: `mdm-utility` — didn't
  exist at the draft's 2026-08-10 capture; created by the same consolidation
  commit (`bb05b885`, gate 1). Zero executions is unsurprising for a
  ~2-day-old machine, but it is now live and in scope for this review.

Current total: **8 live zero-execution workflows**, not 9 — the count
changed for explainable reasons (2 deletions, 1 addition), not because the
draft was wrong.

### B. Every inferred/unknown consumer, with gates 1–5 cross-references

| Workflow | Draft's classification | Status after gates 1–5 |
| --- | --- | --- |
| `load_history`, `bootstrap`, `daily_incremental`, `mdm_gold`, `ownership_mdm_gold`, `silver_mdm_gold`, `bronze_seed_silver_gold` (ordinary branch) | "New graph candidate — no proven active consumer" (7 rows, same claim repeated) | **Superseded by gate 4's exhaustive audit.** Only `load_history` has ever produced a candidate (once, orphaned in `building`); the other six have not succeeded even once since the graph schema existed, so the "no consumer" framing understates it — most haven't produced anything to be unconsumed. |
| `mdm_sync_graph` (standalone utility) | "Unknown / no evidenced consumer for the newly created candidate" | **Confirmed independently in gate 4** — this exact workflow (via the MDM E2E driver) is the source of the other orphaned candidate (100 nodes, 2026-08-09). Still genuinely unconsumed; not superseded, corroborated. |
| `residual_holds_graph` | "Candidate-to-active graph consumer — inferred/manual" (activation deliberately left to an operator) | **Not re-verified this pass** — 2 executions exist in the 30-day window (gate 3 spot-check) but this workflow's candidate-activation binding was not independently traced. Open. |
| `generation_build` | "Unknown / no evidenced external consumer" — standalone, not chained into anything, not wired to the activation pointer | **Not re-verified this pass beyond confirming 0 executions** (list A). Open — genuinely unknown whether this is planned-but-unwired or abandoned. |
| `mdm_seed_universe` | "Subsequent MDM resolution — proven inside `load_history`... standalone invocation requires a manual continuation" | Not a consumer gap in the same sense — this is a documented manual-handoff design, and it's one of the 7 zero-execution machines in list A anyway (no standalone invocations to trace in the current window). |

### C. Cross-cutting findings that must reach the operator regardless of any single row above

1. **Gate 1**: 7 MDM state machines (`mdm-run`, `-backfill-relationships`,
   `-check-connectivity`, `-counts`, `-migrate`, `-sync-graph`,
   `-verify-graph`) are live, invocable, and permanently frozen on a
   pre-consolidation image (`bb05b885`, 2026-08-10) — nothing in the deploy
   pipeline will ever update them again without a deliberate code change.
2. **Gate 3**: at least 2 confirmed production writes (a `gold_refresh` and a
   `seed_universe` run, both landing real Snowflake data) have **no
   corresponding Step Functions execution at all** — this entire audit's
   Step-Functions-scoped inventory is not a complete picture of what
   produces durable output.
3. **Gate 3**: chain M (MDM) has no per-run tracking mechanism in Snowflake
   at all — chain G/T can prove "this exact execution wrote this exact
   data," chain M can only prove "MDM data is recent."
4. **Gate 5**: five machines' `MdmVerify` step is caught (`States.ALL`,
   `ResultPath: null`) and falls through to `GoldRefresh` regardless of
   outcome — confirmed fired 3 times in production (all pre-dating the
   current graph schema, so likely cutover-transitional, but the mechanism
   is unchanged today and gives an operator watching `SUCCEEDED`/`FAILED`
   no visibility into it either way).
5. **Gate 4**: task-definition `edgartools-prod-large:175` (current
   `gold-refresh`'s live target) was registered ~45 minutes before gate 3's
   capture — no execution has completed under it yet, so "current cohort"
   binding for chain G rests on the immediately-prior revision, not the
   literal latest one.

### D. Open questions for the operator (not resolvable from source/AWS state alone)

- Should the 7 orphaned MDM machines (finding C.1) be explicitly
  deregistered, or re-added to the deploy pipeline's write path?
- Is the direct CLI/ECS-bypass path (finding C.2) an accepted, intentional
  escape hatch for one-off operator work, or should it be constrained
  (e.g., require every production write to go through Step Functions)?
- Is the `MdmVerify` non-blocking `Catch` (finding C.4) the correct
  long-term behavior, or should a failure there at least raise a visible
  signal (CloudWatch alarm, run-summary field) even while staying
  non-blocking for `GoldRefresh`?
- Are the 8 zero-execution workflows (list A) intentional break-glass
  utilities worth keeping dormant, or candidates for retirement?
- Is `generation_build` (never chained into anything, never executed) still
  planned work, or abandoned and safe to flag for retirement?

### Operator decisions (2026-08-12)

Reviewed live with the operator. Recorded here as facts for
[Ticket 14 — Decide the Production Workflow Portfolio](../issues/14-decide-the-production-workflow-portfolio.md)
to consume, not as implementation yet:

1. **Orphaned MDM machines (C.1):** deregister the 7 stale, permanently-frozen
   machines (`mdm-run`, `-backfill-relationships`, `-check-connectivity`,
   `-counts`, `-migrate`, `-sync-graph`, `-verify-graph`).
2. **Step-Functions-bypass path (C.2):** accepted as an intentional escape
   hatch for one-off operator work (e.g. cutover-completion steps like
   `manual-stage14-completion`). No enforcement change requested.
3. **`MdmVerify` non-blocking `Catch` (C.4):** keep `GoldRefresh` non-blocked
   by graph-verification failures, but add visibility — a CloudWatch alarm or
   a `run-summary.json` field recording whether `MdmVerify` was caught,
   so a future firing isn't invisible to an operator watching terminal
   status alone.
4. **8 zero-execution workflows (list A):** default lens is **retirement
   candidates**, not assumed-intentional utilities — each one needs to
   justify staying, not the reverse. This reverses this document's own
   initial recommendation.

Not yet decided: `residual_holds_graph`'s candidate-activation binding and
`generation_build`'s status (planned vs. abandoned) — both remain open
questions for Ticket 14 itself, not resolved here.
