# Snowflake Daily Load Trigger — Final Design Summary

Standalone synthesis of the `snowflake-daily-load-trigger` wayfinder map
(`map.md` + issues 01-04 + `research/03-invocation-plumbing-findings.md`).
Written to be handed to an implementer without reading the four tickets
separately.

**Status: design is 3-of-4 complete.** Tickets 01, 02, 03 are resolved.
[Ticket 04 (dead-man's-switch alarm)](issues/04-design-dead-mans-switch-alarm.md)
is **open and was never worked** — see §4. Mode is decision-spec only;
nothing has been built.

---

## 1. The problem

`SNOWFLAKE_RUN_MANIFEST_TASK` — a Snowflake native task defined at
`infra/terraform/snowflake/modules/native_pull/main.tf:719-756` — wakes on a
blind fixed timer (`schedule { minutes = 360 }`) and calls
`EDGARTOOLS_GOLD.PROCESS_RUN_MANIFEST_STREAM()`, which drains any pending
`(workflow_name, run_id)` manifest rows and refreshes the gold layer.

Two things are wrong with a fixed timer:

- **Freshness.** A pipeline that finishes at 12:30 UTC may not be synced into
  Snowflake until up to 6 hours later, for no reason other than where the
  timer happens to sit.
- **Cost.** The 6-hour cadence is itself a scar. It was widened 1 min → 15 min
  → 6 hours by the `ecs-cost-sizing` workstream because a fast poll never let
  the X-Small `EDGARTOOLS_PROD_REFRESH_WH` fully suspend during an active
  backfill, burning ~67 Snowflake credits/week. The timer traded freshness for
  credits because a timer is the only lever a timer gives you.

An event-driven trigger removes the tradeoff entirely: it wakes the warehouse
only when a pipeline has genuinely produced something, so freshness improves
*and* wasted wake-ups go away.

**Scope note:** the trigger's job is to call `PROCESS_RUN_MANIFEST_STREAM()`
at the right moment. Everything downstream of that call — the per-workflow
load and refresh procedures, the manifest inbox table, the Snowpipe that
populates it — is existing, working apparatus and is not being redesigned.

---

## 2. The architecture, end to end

```
  ~7+ gold-affecting Step Functions state machines
  (daily_incremental, load_history, bootstrap, bootstrap_full,
   targeted_resync, full_reconcile, silver_mdm_gold, + see §4 gap G3)
        │
        │  each ends in an ECS `gold-refresh` task, which writes a run
        │  manifest to S3 (SERVING_EXPORT_ROOT)
        │
        ├──────────────────────────────────────────────┐
        │                                              │
        ▼ execution reaches a terminal state           ▼ S3 manifest object
  EventBridge rule                              SNS → Snowpipe
  source: aws.states                            (snowflake_pipe.manifest,
  detail-type: "Step Functions Execution         auto_ingest = true)
                Status Change"                         │
  detail.status ∈ {SUCCEEDED, FAILED,                  ▼
                   ABORTED, TIMED_OUT}          SNOWFLAKE_RUN_MANIFEST_INBOX
  filtered to the watched state-machine ARNs           │
        │                                              ▼
        │                                   SNOWFLAKE_RUN_MANIFEST_STREAM
        ▼                                   (append_only = true; the queue)
  NEW: one-off ECS task — a single-purpose                    ▲
  warehouse CLI command                                       │
        │                                                     │
        │  1. list-executions --status-filter RUNNING          │
        │     across the watched set                           │
        │  2. if anything is still RUNNING → no-op, exit       │
        │  3. if idle → connect via MDM_SNOWFLAKE_SECRET_JSON  │
        │     as EDGARTOOLS_PROD_LOADER                        │
        ▼                                                      │
  CALL EDGARTOOLS_GOLD.PROCESS_RUN_MANIFEST_STREAM() ──────────┘
        │   (drains the stream in one INSERT…SELECT, then per
        │    (workflow_name, run_id): LOAD_EXPORTS_FOR_RUN +
        │    REFRESH_AFTER_LOAD)
        ▼
  EDGARTOOLS_GOLD refreshed
```

**What is removed:** `snowflake_task.manifest_processor` and its
`schedule { minutes = 360 }` block, deleted from Terraform entirely — not
suspended, not kept as a dormant fallback.

**What stays:** the manifest **stream**, the inbox table, the Snowpipe, and
all three stored procedures. The stream is `PROCESS_RUN_MANIFEST_STREAM`'s
*sole* queue (`04_refresh_wrapper.sql:218-221`) — dropping it would zero out
every future call regardless of invoker.

### The two properties the whole design rests on

Worth stating explicitly, because most of the risk analysis in §4/§5 follows
from them:

1. **The stream is a durable queue, not a doorbell.** It is
   `append_only = "true"`, and a Snowflake stream's offset advances only when
   its rows are consumed inside a DML transaction. A fire that arrives when
   the stream is empty is a harmless no-op; rows that arrive *after* a fire
   simply sit pending and are drained by the next one. **A missed fire is
   delayed sync, not lost data** — bounded, in the steady state, by the next
   `daily_incremental` run.
2. **The consuming `INSERT … SELECT` is atomic.** Two concurrent callers
   cannot both process the same manifest rows. This is what lets the design
   skip a distributed lock entirely.

---

## 3. Design decisions and their rationale

| # | Decision | One-line rationale | Source |
|---|---|---|---|
| D1 | Completion signal is the parent **Step Functions execution** reaching a terminal state — *not* the `sec_fetch_active` lease | The lease is released right before `MdmRun`/`GoldRefresh` even start (`deploy-aws-application.sh:3182-3196`), so a free lease says nothing about whether gold was rebuilt | map.md Notes |
| D2 | Watch only gold-affecting state machines, not all 26 | Verification/connectivity utilities never produce gold data; waiting on them would only delay the trigger | map.md Notes (**but the enumeration is wrong — see G3**) |
| D3 | Detection is event-driven (EventBridge on `Step Functions Execution Status Change`), not a second poll | Replacing one poll with another poll defeats the point | map.md Notes |
| D4 | **No daily cap.** Fire on every genuine busy→idle transition; no "already fired today" state anywhere | An empty stream makes the procedure a cheap no-op, and the original credit burn came from a *fixed timer*, not call volume — so a cap buys nothing and costs real freshness. "Once a day" survives as an emergent property of the cron schedule, not an enforced rule | Ticket 01 |
| D5 | Rejected a settle-window debounce | The near-simultaneous-finish case it absorbs is already handled by the RUNNING re-check — a second mechanism for an already-solved problem | Ticket 01 |
| D6 | Compute is a **one-off ECS task on the existing warehouse image**, not Lambda | `grep -r aws_lambda_function infra/terraform/` returns nothing — this repo has zero Lambdas; every workload is ECS/Fargate + Step Functions | Ticket 02 |
| D7 | The re-check/fire step is a **new single-purpose warehouse CLI command**, same shape as `release-sec-fetch-lease` (`COMMAND_REGISTRY` entry, `planned_manifest_paths`/`_resolve_scope` cases) | Reuses the existing image, IAM, deploy pipeline and logging conventions instead of inventing a runtime paradigm for one narrow use case | Ticket 02 |
| D8 | **No ARN-shape filtering** in the EventBridge pattern — react to every terminal event including Distributed Map child/window executions | Filtering on internal AWS Map-run ARN structure is a contract this repo doesn't have, and a filtering bug there fails *silently* by suppressing the one event that mattered; an unfiltered premature fire merely no-ops | Ticket 02 |
| D9 | **No new distributed lock.** Race safety = Snowflake's atomic stream consumption + a fresh RUNNING re-check immediately before firing | Mirrors `_publish_shard_if_remote`'s existing re-read-baseline-right-before-promote pattern; this repo has zero DynamoDB usage, and a lock table would be new infra for a race the stream already closes | Ticket 02 |
| D10 | Invoke via a **direct Snowflake connector `CALL`**, not `EXECUTE TASK` | Bypass the task/stream scheduling mechanism rather than nudge it | map.md Notes |
| D11 | Authenticate as `EDGARTOOLS_PROD_LOADER` via the existing `MDM_SNOWFLAKE_SECRET_JSON` secret — **zero new Snowflake grants** | Live-verified: all three procedures in the chain are `EXECUTE AS OWNER` and owned by that role, which already holds DB/schema USAGE and warehouse USAGE; the live secret's `ROLE`/`WAREHOUSE`/`SCHEMA`/`DATABASE` fields match exactly | Ticket 03 + research |
| D12 | **Remove the task object + schedule from Terraform.** Keep the stream | Break-glass doesn't need the task (an operator can `snow sql -q "CALL … PROCESS_RUN_MANIFEST_STREAM();"`), and removal closes an incident class this repo has hit twice on this exact object (the ticket-99 suspension; the dev go-live schedule-drift 5-whys) | Ticket 03 |
| D13 | The dormant-suspended-task fallback was **available but not chosen** | Snowflake's own docs confirm a schedule-less suspended task is invocable via `EXECUTE TASK` with no `RESUME` — so this was a preference, not a constraint. (`main.tf:730-734`'s comment is imprecise: the schedule requirement applies to `ALTER TASK … RESUME`, not to existence or manual invocation — worth correcting when that file is edited) | Research |
| D14 | Replace the poll with an **alert-only** dead-man's-switch alarm — no fallback execution path | No execution fallback, but yes observability fallback: a broken trigger must surface to an operator instead of gold silently going stale | map.md Notes (**design not done — ticket 04**) |
| D15 | Phase B's `backfill-mdm-entity-ids` sweep needs no separate signal | It's being wired inside `daily_incremental`'s own Stage 2 chain, so that execution's terminal state already implies the sweep ran | map.md Notes |

### Consistency result: D4 and D8 compose correctly

The two decisions most likely to interact badly do not. D8 means a
53-window `load_history` emits ~53 terminal events and therefore ~53
re-checks; every premature one no-ops because the **parent** execution is
still `RUNNING`, so exactly one fire results. D4's absence of a cap is
actively *protective* here rather than additive: under a hard once-per-day
cap, a fire lost to any transient failure would be locked out for the rest of
the day *and* the natural recover-on-next-transition path would be blocked
too. No-cap + no-filtering produces the intended behavior.

Ticket 02 and ticket 03 also describe **one** component, not two — ticket 03
explicitly builds on "the new ECS command (per ticket 02's compute
decision)." There is no second invocation path.

---

## 4. Gaps and open items

### Ticket 04 — the dead-man's-switch alarm (open, and it is the gating one)

By the Destination's own wording, reaching the end of this map required four
things settled. Three are. **This map has not reached its end.**

Leaving ticket 04 to a follow-up ticket is fine. Leaving it *undone while
executing D12's task removal* is not, and this is the sharpest sequencing
point in the whole design: once the 6-hour poll is gone, the alarm is the
only backstop for every failure mode in G1/G2/G3 below. Until then, the poll
is silently masking them.

Its three open sub-questions (what signal, what threshold, where the alert
lands) are still genuinely open. Two notes for whoever picks it up:

- Sub-question 2 ("can the alarm distinguish *nothing to load today* from
  *something was ready and the trigger never fired*") is exactly the detector
  for G2 below. Pending-row age in the manifest inbox is the natural signal
  precisely because it is zero in the benign case and grows in the failure
  case.
- The threshold should be tighter than "eventually." Bounded staleness is
  safe because the stream is durable — but Snowflake streams go **stale** if
  not consumed within the source table's data-retention window. A trigger
  broken for weeks eventually crosses from delayed sync into genuine row
  loss. That is the strongest technical argument for this alarm existing.

### Corrections to `map.md`'s grounding facts

Both of the following contradict statements in `map.md` or ticket 03. Those
files were deliberately not edited (this was a review pass, not a resolution
step), so the corrections live here.

**G3 — the watched set is under-enumerated. `map.md`'s Notes claim the 7
listed state machines match `GOLD_AFFECTING_COMMANDS` "exactly." They do
not.** The map mapped a *command*-level set onto state-machine names by
hand, and `gold-refresh` is a command that appears as the terminal ECS state
in **several** state machines, not just `silver_mdm_gold`. Verified in
`infra/scripts/deploy-aws-application.sh` — every one of these deploys a
state machine whose definition contains a `States.Array('gold-refresh', …)`
ECS state, and none is in the watched 7:

| State machine | Where | Note |
|---|---|---|
| `gold_refresh` | single-workflow loop, line ~4528; command expression line 1256 | **Most important omission.** CLAUDE.md's documented "rebuild gold from existing silver" lever, and the one workflow that is *purely* gold-producing |
| `mdm_gold` | line 4602-4641 | MDM resolution + graph sync + `gold-refresh` |
| `ownership_mdm_gold` | line ~4708 | Distributed-Map batch + MDM tail + `gold-refresh` |
| `bronze_seed_silver_gold` | `write_bronze_seed_silver_gold_definition`, line 3854; gold states at lines 4152 and 4236 | The one-click full-refresh pipeline (cutover Stage 14) |

(`generation_build`, `residual_holds_graph`, and the other remaining
machines were not checked either way — the four above are enough to establish
the finding, but re-derive the list mechanically rather than extending this
table by hand.)

Today the 6-hour poll covers all of them indiscriminately. Under the design
as written, their manifests would sit in the inbox until some *other*,
watched pipeline happens to finish. Not data loss (durable stream), but a
real freshness regression against the thing being replaced.

This is the same failure shape CLAUDE.md's gold-build-memory 5-whys already
documents — `GOLD_AFFECTING_COMMANDS` and `workflow_profile()` described
there as "two independent collections with no link between them." The
EventBridge ARN list is now a **third** such collection, and G3 is that bug
having already occurred, at design time, before a line was written.

*Unmade decision:* enumerate the watched ARNs explicitly in the event pattern
(precise, but rots silently the next time a gold-producing machine is added)
vs. prefix-match `edgartools-prod-*` and filter inside the command (picks up
new machines automatically, but fires re-checks on non-gold machines). Derive
the list mechanically from "which SFN definitions contain a `gold-refresh`
ECS state," not from `GOLD_AFFECTING_COMMANDS`.

**G4 — ticket 03's "zero new grants" is true for Snowflake and false for AWS
plumbing.** The Snowflake half is solid and live-verified. But
`MDM_SNOWFLAKE_SECRET_JSON` is injected **only into the MDM container
definition** (`deploy-aws-application.sh:1125-1134` — that block uses
`$MDM_IMAGE_REF`, `command: ["mdm", "--help"]`, awslogs prefix
`mdm-{profile}`). The **warehouse** task definitions do not carry it. So
ticket 02's "new command on the warehouse image" and ticket 03's "reuse the
secret, same pattern as `mdm export`" do not compose as written: `mdm export`
runs on the MDM task-definition family.

*Good news:* the image itself is not the obstacle. `Dockerfile.warehouse-deps`
installs `--extra s3 --extra mdm-runtime`, and `mdm-runtime` includes
`snowflake-connector-python>=3.7` (`pyproject.toml:59-66`) — the warehouse
image **can** make the connector call. The gap is purely task-definition
wiring: either add `MDM_SNOWFLAKE_SECRET_JSON` to the warehouse container's
`secrets` block (plus `secretsmanager:GetSecretValue` on that ARN for the
warehouse execution role), or run the new command on the MDM task-definition
family, which already has both.

### Cross-ticket gaps found in review

**G1 — a lost fire has no recovery path, because nothing retries.** Ticket 02
analyzed only the false-*idle* race (a new execution not yet visible as
RUNNING → premature fire, self-correcting). It never analyzed the
false-*busy* direction. If the re-check's `list-executions` still shows the
just-terminated execution (eventual consistency), or the ECS task fails to
start, or the connector call errors, that transition's fire is simply gone —
D4 keeps no state, D12 removes the timer, and no ticket specifies a retry.
Bounded by the durable stream to *delayed* sync (next watched completion
drains it), so in steady state ~24h, or ~48h across the Sunday gap in the
`daily_incremental` cron.

*Cheap mitigations:* the event payload carries `detail.executionArn` — the
re-check should explicitly exclude the triggering execution from the RUNNING
set rather than trusting list consistency; and whatever invokes the ECS task
should carry a retry policy (this is one of the reasons the G5 plumbing
choice matters).

**G2 — Snowpipe ingestion latency vs. an immediate fire.** The manifest inbox
is populated *asynchronously*: the gold ECS task writes a manifest to S3 →
SNS → `snowflake_pipe.manifest` (`auto_ingest = true`, `main.tf:660-675`) →
`SNOWFLAKE_RUN_MANIFEST_INBOX` → the stream. The Step Functions execution
reaches SUCCEEDED as soon as the ECS task exits, which can easily be *before*
Snowpipe has ingested. Fire immediately and the stream may still be empty →
`processed_count: 0`. Combined with G1's absent retry, that transition
produces nothing.

This is the failure mode the 6-hour poll structurally masked — it always
retried. No ticket mentions Snowpipe or the inbox→stream lag at all. Again
bounded by stream durability to delayed, not lost. *Cheap mitigations:* have
the command poll `SYSTEM$STREAM_HAS_DATA` for a bounded window before calling
(it needs a warehouse anyway, so the marginal cost is small), or accept the
delay explicitly and let ticket 04's alarm catch the pathological case.

**G5 — the invocation path is left as an unresolved "or."** Ticket 02 says
the command is invoked "as an ECS task from a Step Functions state **or**
directly from the EventBridge rule's target." That choice is never made, and
it is load-bearing for: retry semantics (G1), IAM (an EventBridge→ECS target
needs `ecs:RunTask` + `iam:PassRole`), how `detail.executionArn` reaches the
command (input transformer vs. SFN input), and network/subnet configuration.
The map's Destination promises someone can "build without hitting an
undecided question" — this is one.

**G6 — the task's `WHEN SYSTEM$STREAM_HAS_DATA(…)` guard is silently
dropped.** The removed task carries
`when = "SYSTEM$STREAM_HAS_DATA('…SNOWFLAKE_RUN_MANIFEST_STREAM')"`
(`main.tf:726`, live-confirmed in the research's `SHOW TASKS` output). It is
what keeps the 6-hour timer from waking the warehouse for nothing. The new
path calls the procedure unconditionally. Ticket 01's "cheap no-op" is true
in *procedure* terms, but the `CALL` still resumes
`EDGARTOOLS_PROD_REFRESH_WH` (60s minimum billing) on every fire — including
fires after FAILED/ABORTED executions that produced no manifest at all.
Neither ticket noticed the guard existed. Low severity, but it is a real
regression against `map.md`'s own stated goal of preserving "no wasted
warehouse wake-ups," and it should be a conscious acceptance rather than an
oversight.

**G7 — ticket 02's rationale for D8 rests on an unverified AWS behavior,
though its conclusion survives.** It argues premature fires no-op "because
the parent execution *and sibling windows* still show RUNNING." Verify
whether `list-executions --state-machine-arn` actually enumerates Distributed
Map child executions — the API takes *either* `stateMachineArn` *or*
`mapRunArn`, which suggests children may only be listable under the Map Run.
D8's conclusion holds either way, because the **parent** execution is a
top-level execution and stays RUNNING for the whole Map state. Actionable
half: do not build logic that depends on child executions being listable.

### Not gaps

- The `EDGARTOOLS_DECISION`-style "what about non-gold freshness needs (MDM
  graph sync)" question is explicitly parked in `map.md`'s "Not yet
  specified" and correctly out of scope.
- Watching FAILED/ABORTED/TIMED_OUT as well as SUCCEEDED is deliberate and
  correct — a partially-failed pipeline may still have written manifests.

---

## 5. For the implementer

### Ordered gate — do these in this order

1. **Re-derive the watched ARN list** mechanically from the SFN definitions
   that contain a `gold-refresh` ECS state (G3), and decide explicit
   enumeration vs. prefix-match.
2. **Resolve the invocation path** (G5) and the secret plumbing (G4). Neither
   is a design question; both block writing code.
3. **Build and deploy the trigger alongside the existing 6-hour task.** They
   are not mutually exclusive, and the poll's redundant fires are harmless
   *to correctness* (empty stream → no-op) — though per G6 you pay both
   wake-up profiles until step 5. Running both is the cheapest way to observe
   the new path under real load.
4. **Design and ship ticket 04's alarm.**
5. **Only then remove `snowflake_task.manifest_processor` and its schedule
   from Terraform (D12).** This step is what converts G1/G2/G3 from latent to
   live. Do not run it before step 4.

### Double-check before building

- **The Snowpipe timing window (G2)** is the highest-value thing to measure
  empirically. Instrument the new command to log `processed_count` on every
  fire; a persistent pattern of `0` on genuine transitions is the smoking gun
  and tells you whether the bounded-wait mitigation is needed.
- **`ListExecutions` + Distributed Map (G7)** — one live call answers it.
- **Warehouse wake-ups (G6)** — confirm the credit profile after cutover
  actually beats the 6-hour poll's. The whole cost premise of this map
  depends on it, and the guard that used to enforce it is being deleted.
- **`deploy-snowflake-stack.sh:460-476`** defaults `DBT_SNOWFLAKE_ROLE` to
  `EDGARTOOLS_PROD_DEPLOYER`, and running `--run-dbt` as-is re-flips ownership
  of the gold dynamic tables away from `EDGARTOOLS_PROD_LOADER`. That is a
  live latent risk to the *existing* manifest pipeline (flagged in the ticket
  03 research as adjacent-but-irrelevant), and D11's "the loader owns
  everything so zero grants are needed" premise depends on it not happening.
- **`main.tf:730-734`'s comment** ("Snowflake requires an explicit schedule to
  resume/start a standalone task") is imprecise — true only for
  `ALTER TASK … RESUME`. Correct it while editing that file.
