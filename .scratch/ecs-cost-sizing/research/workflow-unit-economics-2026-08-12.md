# Workflow Unit Economics — 2026-08-12

Scope: Wayfinder Ticket 13 (`ecs-cost-sizing`). Covers all 26 `edgartools-prod-*`
Step Functions state machines from Ticket 11's inventory
([`production-workflow-consumers-source-trace-2026-08-10.md`](production-workflow-consumers-source-trace-2026-08-10.md)),
re-verified by the 2026-08-11/12 gate addendum
([`gate1-gate2-independent-reverification-2026-08-11.md`](gate1-gate2-independent-reverification-2026-08-11.md)).
Region `us-east-1`, account `690839588395`. All new AWS/Snowflake calls in
this pass were read-only (`describe-*`, `get-*`, `list-*`, `SELECT`); no
mutation API was called.

## Evidence reuse and what is new in this pass

Reused without re-deriving, per the ticket's own instruction:

- Fargate pricing basis, rate table, and workload-level cost figures from
  Ticket 02 ([`workload-class-utilization-2026-08-09.md`](workload-class-utilization-2026-08-09.md)).
- The 26-workflow inventory, 30-day execution/retry/duration distribution
  table, and consumer-chain classification from Ticket 11
  ([`production-workflow-consumers-source-trace-2026-08-10.md`](production-workflow-consumers-source-trace-2026-08-10.md))
  and its independent gate re-verification (masked-success findings, graph
  candidate audit, `Catch` firing evidence).
- The full loop/record-funnel inventory from Ticket 12
  ([`loop-inventory-and-funnel-2026-08-12.md`](loop-inventory-and-funnel-2026-08-12.md)),
  including the Distributed Map child-`run_id` traceability gap and the
  masked-success finding for `ticket42-task35-fulluniverse-retry5-1786380966`.

New evidence gathered this pass (all cited inline with exact command/ARN/timestamp):

1. AWS Step Functions Standard-workflow state-transition pricing (Pricing API + public pricing page).
2. CloudWatch Logs ingestion/storage pricing and this account's current log-group byte volume.
3. Exact per-task Fargate billing (`PullStartedAt`→`StoppedAt`, reserved CPU/memory) extracted directly from `aws stepfunctions get-execution-history` for 19 executions spanning 17 of the 26 workflows (the other 9 have zero executions ever/in-window — see §Zero-execution workflows).
4. Parent-level Step Functions state-transition counts for the same 19 executions, plus a bounded child-transition estimate for the two Distributed-Map-heavy workflows.
5. Direct confirmation, via AWS documentation, of how Distributed Map `ExecutionType: STANDARD` children are billed.
6. Four new `SNOWFLAKE_REFRESH_STATUS` and `MDM_RELATIONSHIP_INSTANCE` queries binding specific executions (or ruling out a binding) to committed/exported record counts not already captured in Ticket 12.

## Pricing basis

### Fargate (reused from Ticket 02, unchanged)

`compute_cost = billed_seconds * (reserved_vCPU * $0.000011244 + reserved_GB * $0.000001235)`,
billed seconds = `ceil(StoppedAt − PullStartedAt)` in seconds, 60-second Linux
minimum. Source: [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/),
US East (N. Virginia), Linux/x86 (this account's tasks run without
`runtimePlatform`, which defaults to Linux/X86_64 per
[ECS task definition parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html)).

| Profile | CPU/Memory | Per-task-hour |
| --- | --- | ---: |
| small (warehouse or MDM) | 512/1024 | $0.0246852 |
| medium (warehouse or MDM) | 1024/4096 | $0.0582624 |
| large (warehouse or MDM) | 2048/8192 | $0.1165248 |
| historical MDM medium (pre-2026-07 revisions, e.g. `mdm-medium:58/66`) | 1024/2048 | $0.0493704 |

**Tier-invariance note (load-bearing for every figure below):** this evidence
spans task-definition revisions from `large:90` through `large:178`,
`medium:95` through `medium:177`, and `mdm-medium:45` through `mdm-medium:149`,
captured across three prior tickets and this one. Fargate bills **reserved**
CPU/memory, and small/medium/large's reservations (512/1024, 1024/4096,
2048/8192) are unchanged across every one of those revisions — confirmed by
reading each task's own `Cpu`/`Memory` fields directly out of its execution
history (§Method below), not assumed from a revision number. A cost figure
computed from an execution on `large:120` is therefore valid at today's
`large:178` (or `:165`, Ticket 11's captured cohort, or `:175`, gate 3's
zero-execution current revision) **at the same tier**. The one documented
exception is the **historical** MDM medium at 1 vCPU/2 GiB (superseded before
2026-07-25 per Ticket 02) — those specific historical figures use the old
rate, called out explicitly wherever they appear.

### Step Functions Standard workflows (new)

```
aws pricing get-products --service-code AmazonStates --region us-east-1 \
  --filters "Type=TERM_MATCH,Field=usagetype,Value=USE1-StateTransition"
```
→ SKU `5NX6NBD43SV57CH3`, `"$0.000025 per state transition"`, effective
2025-07-01, publication 2025-08-28. Cross-confirmed against
[aws.amazon.com/step-functions/pricing](https://aws.amazon.com/step-functions/pricing/)
(fetched 2026-08-12): `"$0.000025"` per state transition in US East (N.
Virginia); free tier `"4,000 free state transitions per month"`, which "does
not automatically expire." **This report prices state transitions at the
gross marginal rate ($0.000025/transition), not net of the free tier** — the
free tier is a portfolio-level monthly credit, not something attributable to
one workflow's unit economics, and (as shown below) it dwarfs this
portfolio's actual usage regardless.

Billing definition, quoted verbatim from the pricing page: *"Step Functions
counts a state transition each time a step of your workflow is executed,"*
illustrated by "counting the nodes on the graph, including Start and End
nodes." This report's proxy, applied uniformly: **transitions = 1 (execution
start) + count of `*StateEntered` events** in `get-execution-history`.
Verified this proxy is retry-insensitive: `bootstrap-ticket03-verify-1785426021`
had 4 `TaskFailed` retries on its `MdmVerify` step but generated no
additional `TaskStateEntered` events — Step Functions retries cost nothing in
transitions, only in re-run Fargate compute (see per-workflow retry costs
below).

**Distributed Map child billing, checked before using it (per this ticket's
own risk note):**
[docs.aws.amazon.com/step-functions/.../state-map-distributed.html](https://docs.aws.amazon.com/step-functions/latest/dg/state-map-distributed.html)
states plainly: *"Each child workflow execution has its own, separate
execution history from that of the parent workflow."* Combined with
[choosing-workflow-type.md](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-standard-vs-express.html):
*"Standard Workflow executions are billed according to the number of state
transitions processed."* Every Distributed Map in this account uses
`ExecutionType: STANDARD` (confirmed live in gate 1-2's re-verification and
re-confirmed here by pulling `load-history`'s and `bronze-seed-silver-gold`'s
live ASL and inspecting every `Map` state's `ItemProcessor`) — so each child
is a separately-billed Standard execution.

**Magnitude check, run before building any per-child accounting (per this
ticket's advisory):** every Distributed Map's `ItemProcessor` in this
account's live ASL has exactly **one** inner state (`RunWindow`,
`RunFundamentalsEntityFacts`/`PerFiling`/`ThirteenF`, or the `bootstrap-batch`
task state) — confirmed by parsing `load-history.json`'s and `bssg.json`'s
live definitions (`aws stepfunctions describe-state-machine`, captured
2026-08-12). One inner state ⇒ 2 transitions per child (1 start + 1
`StateEntered`). At up to 53 children per map (`load_history`'s
`WindowedBootstrap`/Stage 1B) or 680 (`bronze_seed_silver_gold`'s/
`silver_mdm_gold`'s `StrictBatchSilver`/`BatchSilver`), the **most
Map-heavy single execution in this portfolio** costs at most
`680 × 2 × $0.000025 = $0.034` in child transitions, and a fully-succeeding
`load_history` run (4 maps × 53 × 2 × $0.000025) costs at most `$0.0106`.
Both are three to four orders of magnitude below every workflow's Fargate
compute cost reported below (all ≥ $0.0004, most ≥ $0.001, several ≥ $0.1).
**Conclusion: Step Functions state-transition cost is immaterial to this
portfolio's unit economics in every case.** It is reported once per workflow
below (exact, parent-level, computed the same way for every execution) plus
this one bounded child estimate — not itemized per child.

### CloudWatch Logs (new)

```
aws logs describe-log-groups --log-group-name-prefix /aws/ecs/edgartools-prod
aws logs describe-log-groups --log-group-name-prefix /aws/states/edgartools-prod
```
captured 2026-08-12: `/aws/ecs/edgartools-prod-warehouse` (568,206,308 bytes),
`/aws/states/edgartools-prod-warehouse` (21,881,484 bytes),
`/aws/ecs/containerinsights/edgartools-prod-warehouse/performance`
(10,325,727 bytes) — all `retentionInDays: 7`. Total **600,413,519 bytes
(≈ 0.56 GiB)** currently stored, i.e. everything the portfolio has ingested
in roughly the trailing week (PR #401's 7-day retention enforcement, per
CLAUDE.md and the Ticket 11 handoff).

Rates: `aws pricing get-products --service-code AmazonCloudWatch --region
us-east-1 --filters "Type=TERM_MATCH,Field=usagetype,Value=USE1-DataProcessing-Bytes"`
→ `"$0.50 per GB custom log data ingested in Standard log class - US East
(Northern Virginia)"`. Storage rate ($0.03/GB-month, archived) confirmed via
[aws.amazon.com/cloudwatch/pricing](https://aws.amazon.com/cloudwatch/pricing/)
(not independently found in the Pricing API this pass). At $0.50/GB, the
trailing week's ~0.56 GiB of ingestion is worth **≈ $0.30**; projected across
a month (×4.3) ≈ **$1.29/month** — this is a portfolio-wide upper bound
(everything currently stored, valued as if freshly ingested), not a
per-workflow figure, because CloudWatch retention makes per-execution log
byte counts unrecoverable once 7 days pass (the same gap Ticket 12
documented for record-level log evidence). **Verdict: logging overhead is
not material** at current volume — under $1.30/month against a portfolio
whose single most expensive traced execution alone cost over $2 (see
`load_history` below).

**S3 manifest overhead, bounded rather than skipped:** `gold_refresh` writes
one run manifest plus 23 table exports per successful run (Ticket 11's chain
G description, confirmed by the 23-table `TABLES_LOADED` figure in every
`SNOWFLAKE_REFRESH_STATUS` row captured below). At S3's $0.005/1,000 PUT +
$0.0004/1,000 GET requests, ~24 PUTs and a comparable number of GETs
(Snowpipe's own ingestion, not separately measured) per run costs on the
order of **$0.0001 per run** — genuinely negligible, stated with its input
count rather than asserted bare.

## Method for per-execution Fargate cost, state transitions, and records

For 19 named executions (reusing execution names already identified by
Tickets 02/11/12 — no fresh `list-executions` scan beyond confirming each
workflow's most recent entries), this pass ran
`aws stepfunctions get-execution-history --execution-arn <arn> --max-results 1000`
and parsed every `TaskSucceeded`/`TaskFailed` event's embedded ECS `runTask.sync`
result (a complete `DescribeTasks`-shaped JSON object, including `Cpu`,
`Memory`, `PullStartedAt`, `StoppedAt`, `TaskDefinitionArn`, and the container
command override) directly out of Step Functions' own execution history —
**no separate ECS or CloudWatch call was needed for task-level billing
inputs**, and unlike CloudWatch Logs' 7-day retention, Step Functions retains
full execution history for Standard workflows for **90 days**
([Standard vs Express](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-standard-vs-express.html):
*"up to 90 days after your execution completes"*), which is why this pass
could still cost exact 17-day-old executions (`edge09-employed-by-postfix3`,
`edge11-institutional-holds-fullrun`) that Ticket 12 had already flagged as
outside CloudWatch's log-retention window for record-level detail.

Extraction script: `cost_extract.py` (scratchpad, not committed — logic
reproduced inline below for auditability). Full per-task output for all 19
executions is in this pass's scratchpad (`cost_extract_output.txt`); every
number quoted below traces to one row of that output.

```
billed_seconds = max(60, ceil((StoppedAt_ms − PullStartedAt_ms) / 1000))
cost = billed_seconds * ((Cpu/1024) * 0.000011244 + (Memory/1024) * 0.000001235)
```

Sanity-checked against Ticket 02's independently-computed figures for the
same underlying executions before trusting it at scale: `daily-incremental`'s
main command (9,549 billed seconds, `large`) → **$0.309082** here vs. Ticket
02's **$0.3091**; `bronze-seed-silver-gold-1786226258`'s `mdm run
--entity-type all` (44,227 billed seconds, historical `mdm-medium:138`,
1 vCPU/4 GiB — already the current-generation memory size, not the 2 GiB
historical exception) → **$0.715770** here vs. Ticket 02's **$0.7158**;
`mdm-check-connectivity` (60 billed seconds, `mdm-small`) → **$0.000411**
here, matching Ticket 02's bounded-MDM-chain `mdm counts` line item exactly
(same profile, same billed floor). All three independent cross-checks agree
to 4+ significant figures.

---

## Composite production pipelines

### `load_history` — the flagship masked-success execution, fully costed

Execution: `ticket42-task35-fulluniverse-retry5-1786380966`, **FAILED**,
2026-08-10T12:56:08 → 2026-08-11T19:19:22 (-04:00) = **30h23m14s
end-to-end**. This is the same execution Ticket 12 identified as committing
~21M gold rows despite terminal `FAILED` status — reused here as the primary
costed instance because it is the only current-digest `load_history`
execution with a complete stage-by-stage map-run trace already established.

**Stage costs** (`large` = 2 vCPU/8 GiB throughout):

| Stage | Type | Window | Duration | Items | Cost method | Cost |
| --- | --- | --- | --- | ---: | --- | ---: |
| Parent-level tasks (leases, seed-universe, mdm seed-universe, compute-windows, ADV/roster fetch+ingest, mdm run/backfill/export/sync, verify-graph ×4 failed, gold-refresh, write-run-summary ×4 failed) | 23 discrete ECS tasks | full execution | 7,514 billed-sec summed | 23 tasks | exact, `get-execution-history` | **$0.153707** |
| `Stage0CompanyIdentity` (Map, now removed from current source — see below) | Distributed Map, `MaxConcurrency:1` | 13:16:12→15:06:30 | 1h50m18s | 53/53 succeeded | wall-clock = summed child billable time (concurrency 1 ⇒ Ticket 02's "wall-clock÷concurrency invalid" warning does not apply) | **$0.2142** |
| `WindowedBootstrap` (Map) | Distributed Map, `MaxConcurrency:1` | 15:42:28→06:12:21(+1d) | 14h29m53s | 53/53 succeeded | same method | **$1.6894** |
| `Stage1BEntityFacts`/`PerFiling`/`ThirteenF` (3 Maps) | Distributed Map, `MaxConcurrency:1` | 06:12:21→17:35:08 (sequential) | 11h22m47s combined | **0 succeeded / 1 failed / 1 aborted / 51 pending each** — only ~2 of up to 159 possible children ever started | **not resolved to child level this pass** — see caveat | **$0.01–$1.33 (bounded, not point-measured)** |
| Parent + child state transitions | 40 parent (1+39 `StateEntered`) + ≤224 child (112 real children × 2, using the item counts above, not the nominal 53×3) | — | — | 264 transitions | exact formula above | **$0.0066** |

**Stage1B cost caveat, stated explicitly rather than estimated as a point
value:** unlike `Stage0`/`WindowedBootstrap` (53/53 succeeded — wall-clock
genuinely reflects 53 sequential large-task occupancies at `MaxConcurrency:1`),
Stage 1B's `itemCounts` (`0 succeeded/1 failed/1 aborted/51 pending`, all
three maps) mean **at most 2 children per map ever actually launched**; 51 of
53 never started and cost nothing. Treating each map's full wall-clock window
as continuous large-task occupancy — as is valid for Stage 0/`WindowedBootstrap`
— would overstate Stage 1B's cost by roughly 25×. This pass did not query the
individual child executions (would require locating up to 6 child execution
ARNs via the same traceability workaround Ticket 12 used for logs, not
attempted this pass — see Limitations), so Stage 1B's true cost is reported
as a bounded range: **upper bound $1.3260** (11h22m47s combined wall-clock ×
`large`'s $0.1165248/hr, i.e. treating the whole window as continuously
billed) down to **≈$0.01–0.05** (2 large-task launches of a few minutes each,
consistent with "a single root-cause bug hit immediately on window 1," per
Ticket 12) as a lower bound.

**Total execution cost: $2.07–$3.39**, dominated by the two fully-succeeded
Distributed Maps ($1.90 combined, 92% of the low-end total) and the
parent-level MDM/export chain ($0.154). State transitions (≤$0.007) are
immaterial, as established above.

**A stale-source note surfaced by this same evidence, orthogonal to cost:**
`Stage0CompanyIdentity` was removed from `load_history`'s current source by
PR #396 (commit `da8ccb65`, 2026-08-10T18:35:39-04:00) — **3.5 hours after**
this execution's `Stage0CompanyIdentity` pass ran (13:16–15:06 that same
day). The $0.2142 attributed to it above is real, historical, execution-bound
cost for a stage that no longer exists in current source (already flagged by
Ticket 12; repeated here because it changes what "load_history's current
cost shape" means — a fresh run today has 3 Distributed Maps in its Stage
1/1B, not 4, and would not pay Stage 0's $0.2142 line item at all).

**A new critical-path finding from this pass, not previously documented:**
tracing the execution's final 53 minutes event-by-event
(`get-execution-history`, `TaskStateEntered`/`TaskFailed`/`TaskScheduled`
timestamps) shows **two separate exhausted-retry sequences**, not one:

1. `MdmVerify` entered 18:16:35, 4 attempts (537s/308s/278s/299s billed,
   $0.00368+$0.00211+$0.00191+$0.00205 = **$0.00975**) with retry backoff
   gaps of 120s/240s/480s between them (matching the `IntervalSeconds:120,
   BackoffRate:2.0, MaxAttempts:3` policy documented elsewhere in this
   repo), exhausted at 18:55:29, then **caught** (`States.ALL` →
   `GoldRefresh`, per gate 5's already-documented mechanism) — **this is
   gate 5's third confirmed live `Catch` firing**, now traced to its exact
   sub-second timeline rather than just confirmed to have occurred.
2. `GoldRefresh` then runs 18:55:29→18:58:24 (175s wall / 160s billed,
   **$0.005179**) and **succeeds** — this is the moment the ~21M gold rows
   were durably committed.
3. `WriteRunSummary` (a pure bookkeeping step — writes an operator-facing
   run summary, not a data product) then runs 18:58:24→19:19:22, **4 more
   exhausted attempts** (67s/86s/77s/88s billed, $0.00423 total), **with no
   `Catch`** — its final failure at 19:19:22 is what terminates the entire
   30h23m execution as `FAILED`.

**This is a new, independently-derived finding, distinct from (though
compatible with) Ticket 12's and gate 5's:** the execution's `FAILED`
terminal status is attributable specifically to `WriteRunSummary` — a
non-data-producing bookkeeping step — failing **after** the actual valuable
output (20,966,689 gold rows) had already been durably committed via a
`Catch`-protected `MdmVerify`→`GoldRefresh` path. An operator reading only
the terminal status would not just underestimate the value produced (Ticket
12's point); they would also misattribute *why* it failed, since the failure
occurred in a step that runs after all value-producing work is already done.

**Records:** `SNOWFLAKE_REFRESH_STATUS` re-queried live this pass
(`snow sql --connection edgartools-prod`, 2026-08-12) shows this exact
`RUN_ID` at **`STATUS: running`**, `SOURCE_ROW_COUNT: 20,966,689`,
`TABLES_LOADED: 23` — **this contradicts Ticket 12/gate 3's same-day
2026-08-12 capture, which recorded `STATUS: succeeded` for the identical
`RUN_ID`.** Both captures are real, timestamped snapshots of a
live-mutable status field; this is not a data-quality bug in either report,
but it means "succeeded" was not a permanently stable terminal state for
this row at the time gate 3 read it — flagged here as a fresh, unresolved
observation rather than silently preferring one snapshot over the other. The
same query also newly confirms this execution's embedded `seed-universe`
sub-stage: `RUN_ID = ticket42-task35-fulluniverse-retry5-1786380966,
SOURCE_WORKFLOW = seed_universe, STATUS: succeeded, SOURCE_ROW_COUNT: 10,398,
TABLES_LOADED: 1` — the first time this pass (or any prior ticket) has bound
`seed_universe`'s row count to a genuine Step Functions execution rather than
the CLI-bypass example gate 3 used.

Combined with Ticket 12's numbers: 201,154 silver rows (`WindowedBootstrap`'s
accession loop), 10,398 ticker rows, 20,966,689 total gold+source rows in
Snowflake after this run's manifest (a **snapshot total across all 23
tables**, not this execution's incremental delta — `gold_refresh` always
rebuilds/re-exports the complete current table set from silver, so this
number cannot be read as "new rows this run produced").

**Cost per 1,000 records, both denominators, both stated with their
caveat:**

- **Per 1,000 silver rows** (the record type this execution's own Stage 0/1
  work actually produced): $1.9036 (the two fully-succeeded Maps) /
  201.154 = **$9.46 per 1,000 silver rows**.
- **Per 1,000 gold-snapshot rows**: $2.07–$3.39 (total) / 20,966.689 =
  **$0.0001–$0.0002 per 1,000 rows** — near-zero, because this reflects a
  full-table re-export whose cost is fixed per run, not scaled to the
  20.97M-row snapshot size (see `gold_refresh` below for the cleanest
  isolated example of this same fixed-cost pattern).

**Records/sec:** within `WindowedBootstrap`'s own 52,193s window: 201,154
silver rows / 52,193s = **3.85 rows/sec**; against the full 109,394s
execution wall-clock: **1.84 rows/sec**. Both are throttled by real,
rate-limited SEC network fetching at `MaxConcurrency:1` (55,269 accessions
attempted, 114,172 document-level fetches, per Ticket 12) — contrast with
`bronze_seed_silver_gold`'s `StrictBatchSilver` below, which reprocesses
already-captured bronze with **zero new SEC calls** at `MaxConcurrency:20`
and is ~100× faster per record.

**Failure rate (30-day, Ticket 11):** `load-history` 13 runs — 2 succeeded /
8 failed / 3 aborted (15.4% terminal-succeeded). Given this section's own
finding, terminal status understates delivered value for at least this one
instance.

---

### `bronze_seed_silver_gold` — two evidenced shapes: a genuine zero-commit failure and a validated high-throughput Map

**Instance (a): the full-MDM-run failure, freshly costed this pass.**
Execution `bronze-seed-silver-gold-1786226258`, **FAILED**,
2026-08-08T17:57:39 → 2026-08-09T07:36:22 (-04:00) = **13h38m43s**.
7 parent-level tasks: `seed-bronze-batches` (93s billed, $0.001505),
`mdm run --entity-type all` (44,227s billed, $0.715770 — the historical
full-universe run already documented in Ticket 02), `mdm backfill-relationships`
(493s, $0.007979), then **`mdm export` failed 4 consecutive times**
(76s/70s/70s/77s billed, $0.001230+$0.001133+$0.001133+$0.001246 =
$0.004742) with **no `Catch`** on this step — the execution stops here.
**Total parent cost: $0.729996.** State transitions: 9 (1+8 `StateEntered`),
$0.000225 — negligible.

**This execution never reached `MdmVerify`, `GoldRefresh`, or any Snowflake
commit.** Confirmed directly: `SELECT ... WHERE RUN_ID LIKE '%1786226258%'`
against `SNOWFLAKE_REFRESH_STATUS` returns **no rows** (queried live this
pass, 2026-08-12; this execution's 2026-08-08 timestamp is safely inside the
tracking table's history, which starts 2026-08-07 — so this is a genuine
"no row exists," not a pre-tracking-table gap). **This is the mirror image
of `load_history` retry5 above: real, substantial compute cost ($0.73, 44,227
of the 45,106 total billed-seconds spent on one `mdm run` task) followed by a
genuine terminal failure with zero downstream commit** — not masked, not
partially successful, a clean total loss on this execution's own $0.73.

**Instance (b): the `StrictBatchSilver` Map, reused from Ticket 02 for
record-bound cost (not re-derived this pass).** Execution
`bronze-seed-silver-gold-medium-20-retry-1786214600`, **ABORTED** by the
operator after the Map completed (a profile/concurrency validation run per
Ticket 02, not a production delivery run) — `680/680 succeeded, 0 failed`,
52m06s wall-clock, `MaxConcurrency:20`. Ticket 02's own explicit warning
applies here (`Map wall-clock ÷ concurrency is not a valid cost
calculation`): the reused cost is the **summed-child-billable-seconds upper
bound, $0.9912** (61,245 seconds across 680 children, `medium` = 1 vCPU/
4 GiB), not a wall-clock-derived figure. Records (Ticket 12 §4, same
execution): 67,807 CIKs, 71,778 raw bronze objects, **1,259,036 silver rows
written**, 50,801 skipped, **0 network fetches** (confirms `--artifact-policy
skip`).

**Cost per 1,000 silver rows (instance b): $0.9912 / 1,259.036 = $0.787 per
1,000 rows** — roughly 12× cheaper per row than `load_history`'s Stage 0/1
($9.46/1,000), because this Map reprocesses already-captured bronze at
`MaxConcurrency:20` with zero new SEC network calls, versus `load_history`'s
real, rate-limited SEC fetching at `MaxConcurrency:1`.

**Records/sec (instance b): 1,259,036 / 3,126s (52m06s) = 402.8 rows/sec** —
~105× `load_history`'s 3.85 rows/sec within its equivalent stage. This is the
clearest evidenced illustration in this portfolio of records/sec depending
almost entirely on whether a stage does real network I/O or reprocesses
existing data, not on task profile or Map concurrency alone.

**Failure rate (30-day, Ticket 11):** 37 runs — 1 succeeded / 26 failed / 10
aborted (2.7% terminal-succeeded) — the lowest success rate of any workflow
with meaningful volume in the portfolio.

---

### `daily_incremental` — the only recurring-cadence workflow, costed but not currently running

Execution: `daily-incremental-ticket89-unblocked-1785856213`, **SUCCEEDED**,
2026-08-04T11:10:16 → 16:00:57 (-04:00) = **4h50m41s**. 26 parent-level
tasks (no Distributed Map in this workflow's ASL — confirmed 0
`mapRunStarted` events... actually 1 `mapRunStarted` was recorded in the raw
type count but not resolved to a record-bearing map this pass; see
Limitations). **Total cost: $0.385757** (14,549 billed-seconds summed,
23,925.5 vCPU-sec, 94,525 GB-sec). Dominated by the main
`daily-incremental --recurring-index-lookback-days 7` command itself: 9,549
billed-sec on `large`, **$0.309082** (80.1% of total execution cost) —
cross-checked exactly against Ticket 02's independently-derived $0.3091 for
this same task.

**This execution is one of gate 5's three confirmed live `MdmVerify` `Catch`
firings** (4 `TaskFailed` on `mdm verify-graph`, $0.00226+$0.00195+$0.00191+
$0.00195 = $0.00807, then caught, `GoldRefresh` ran and succeeded, $154s
billed, $0.004629) — reused directly from gate 5, not re-derived. Also shows
4 `TaskFailed` on `release-sec-fetch-lease` and 4 on
`release-identity-refresh-lease` (both non-fatal cleanup steps whose retries
add $0.0197 combined but do not block or mask anything further downstream).

**Records:** `SNOWFLAKE_REFRESH_STATUS` queried live this pass for this exact
`RUN_ID` — **no row exists** (2026-08-04 predates the tracking table's own
2026-08-07 earliest row; this is a genuine pre-tracking-table evidence gap,
not a masked-failure finding like `bronze_seed_silver_gold` instance (a)
above — the `GoldRefresh` ECS task did succeed here, but whether it landed a
Snowflake manifest cannot be confirmed for this specific execution).

**State transitions:** 35 (1+34 `StateEntered`), $0.000875 — negligible.

**Failure rate / freshness (30-day, Ticket 11):** 13 runs — 3 succeeded / 6
failed / 4 aborted (23.1% terminal-succeeded). **Most consequential finding,
reused directly from Ticket 12 §5, restated here because it bears directly
on this workflow's *freshness contribution*, which this ticket is asked to
report:** `daily_incremental` — the workflow CLAUDE.md and this workstream
document as the production daily-cadence pipeline — **has had zero
executions in the trailing 8 days** as of the 2026-08-12 capture (most recent
entry `daily-incremental-ticket89-unblocked-1785856213`, 2026-08-04). Its
freshness contribution to the gold layer is currently **zero, dormant**, not
merely "costly when it runs."

---

### `bootstrap` — the shortest fully-evidenced Catch example

Execution: `bootstrap-ticket03-verify-1785426021`, **SUCCEEDED**,
2026-07-30T11:40:24 → 15:50:07 (-04:00) = **4h9m43s**. 11 parent-level
tasks, **total cost $0.381558** (13,968 billed-sec, 23,663.5 vCPU-sec,
93,511 GB-sec) — dominated by `bootstrap` itself (10,093s billed on `large`,
**$0.326690**, 85.6% of total). Also one of gate 5's three confirmed
`MdmVerify` `Catch` firings (4 `TaskFailed`, $0.00779 combined, then caught;
`GoldRefresh` ran 174s billed, $0.005632). No Distributed Map (0
`mapRunStarted` events, confirmed directly this pass). State transitions: 9
(1+8), $0.000225.

**Records:** predates the `SNOWFLAKE_REFRESH_STATUS` tracking table
(2026-07-30, before its 2026-08-07 earliest row) — not reconstructable this
pass, stated explicitly rather than guessed.

**Failure rate (30-day, Ticket 11):** 1 run — 1 succeeded / 0 failed / 0
aborted. This is the only execution of `bootstrap` in the 30-day window, so
the 100% success rate is a single data point, not a distribution.

---

### `residual_holds_graph` — a genuinely cheap failed-attempt-then-success pair

Two executions, both costed this pass:

**Attempt 1** (`residual-holds-20260725T221723Z`, **FAILED**): 3 `TaskFailed`
on `mdm run --entity-type security`, old `mdm-medium:66` (1 vCPU/2 GiB, the
**historical exception rate**, $0.0493704/hr), 68s/60s/60s billed — **all
three OOM-killed** (per Ticket 02's already-documented finding) — **total
cost $0.002578**. This is the cheapest documented failure in the whole
portfolio: three genuine crash-loop attempts cost a quarter of a cent
combined before the operator switched profiles.

**Attempt 2** (`residual-holds-20260725T222735Z`, **FAILED at verification,
not at the heavy stages**): 1 image-pull `TaskFailed` (60s, $0.001942, `mdm-large`
1 vCPU→2 vCPU/8 GiB now), then **8 heavy stages succeeded** on `mdm-large`
(security 1,875s $0.060690, person 337s $0.010908, `IS_INSIDER` 127s
$0.004111, `HOLDS` 642s $0.020780, `COMPANY_HOLDS` 249s $0.008060,
`INSTITUTIONAL_HOLDS` 62s $0.002054, export 915s $0.029617, sync 67s
$0.002169 = **$0.138389** for the 8 successful stages), then 3
`TaskFailed` on `mdm verify-graph --skip-native-app` (80s/65s/63s, $0.000549+
$0.000446+$0.000432 = $0.001427) — verification failed 3 times and this
step has **no `Catch`**, so the execution terminates `FAILED` even though
all 8 data-producing stages succeeded. **Total attempt-2 cost: $0.141709.**

**Combined workflow cost across both attempts: $0.144287.** State
transitions negligible in both (10 total, $0.00025 + a comparable amount for
attempt 1).

**Records:** the candidate this execution built is not independently
Snowflake-bound (per Ticket 11's own classification — activation is
deliberately operator-driven, not automatic) and its generation predates the
current graph schema (recreated 2026-08-07/09, per CLAUDE.md's documented
incident) — not reconstructable from current Snowflake state. CLAUDE.md's
own residual-holds note cites a later, separate manual sync/verify reaching
193,323 nodes/166,067 edges — not from this execution's own automatic path,
reused here only as context, not as this execution's bound output.

**Failure rate (30-day, Ticket 11):** 2 runs, 0 succeeded / 2 failed / 0
aborted (0% terminal-succeeded across all executions ever, per gate 3).
Despite 0% terminal success, 8 of 9 heavy data-producing stages across the
two attempts did complete — a workflow whose terminal-status failure rate
substantially overstates its actual work-loss rate.

---

### `ownership_mdm_gold` — zero reconstructable Fargate cost, by design of the abort

Only execution in the 30-day window: `ownership-mdm-gold-10cik-20260725T204806Z`,
**ABORTED**, 2026-07-25T16:48:09 → 17:06:09 (18m0s wall-clock). Its execution
history contains `TaskStarted`/`TaskSubmitted` for the one task that began,
but **no `TaskSucceeded`/`TaskFailed`/`TaskAborted` event with an embedded
ECS result** — the operator's `StopExecution` call appears to have
interrupted the task before Step Functions recorded its terminal ECS state.
**Fargate cost for this execution genuinely cannot be reconstructed from
Step Functions history** (stated explicitly, not defaulted to $0) — the
running task almost certainly incurred some real cost, but its billed-seconds
are not recoverable this way, and the task is far too old (18 days) for
`aws ecs describe-tasks` to return it. State transitions: 2 (1+1
`StateEntered`), $0.00005 — this part is exact regardless.

**Failure rate (30-day):** 1 run, 0/0/1 (100% aborted).

---

### `silver_mdm_gold`, `mdm_gold`, `generation_build` — one real execution among the three

`silver_mdm_gold`'s `BatchSilver` Map has **zero executions ever**
(re-confirmed live this pass: `aws stepfunctions list-executions` returns
`[]`) — genuinely $0 spent, not unreconstructable; see §Zero-execution
workflows. `mdm_gold` likewise has zero executions in the 30-day window
(Ticket 11) and this pass's fresh `list-executions` call also returns `[]`.

`generation_build` has exactly **one execution ever**:
`ticket20-e2e-validate5-20260722T203009-generation-build`, **SUCCEEDED**,
2026-07-22T20:30:14→20:36:52 = **6m38s**. 3 parent-level tasks:
`mdm generation-plan` (60s billed, `mdm-medium` 1 vCPU/2 GiB — historical
rate, $0.000823), `mdm generation-fan-in` (60s, `mdm-small`, $0.000411),
`mdm generation-activate` (60s, `mdm-small`, $0.000411). **Total: $0.001646**
— the cheapest complete (non-aborted, non-failed) workflow execution in this
entire portfolio. Its `BuildPartitions` Distributed Map (17 partitions per
Ticket 12 §7) ran as a child of this execution but its own record/cost
detail is outside the 90-day Step Functions history window as of this
capture (2026-07-22 is 21 days old — inside the 90-day Standard-workflow
retention, but this pass did not pursue the individual child executions;
flagged as available-but-not-pursued, distinct from genuinely
unreconstructable). Records: the generation this run produced
(`056426c8-538d-4c32-9030-bcadced29e24`) no longer exists in the current
`GRAPH_GENERATION` table (schema recreated 2026-08-07/09) — not
reconstructable. State transitions: 9 (1+8), $0.000225.

**Failure rate:** 1/1 succeeded, its only-ever execution.

---

## Warehouse-only and base workflows

### `gold_refresh` — the clean fixed-orchestration-cost example

Execution `gold-refresh-stage15-1786285678`, **SUCCEEDED**,
2026-08-09T10:28:01→10:30:43 (-04:00) = **2m42s end-to-end**, 1 parent
task (151s billed, `large`, **$0.004888** — cross-checked against Ticket 02's
$0.00547 for the same task; the small difference is expected rounding/task-
revision drift, both independently derived from the same underlying
`PullStartedAt`/`StoppedAt` pair). State transitions: 2 (1+1), $0.00005.

**This is the cleanest "fixed orchestration cost, record-volume-independent"
example in the portfolio, as the ticket asks to isolate.** `SNOWFLAKE_REFRESH_STATUS`
binds this exact `RUN_ID` to **20,866,603 rows across 23 tables**
(gate 3, re-confirmed live this pass — this row's `STATUS` is still
`succeeded` as queried 2026-08-12, unlike `load_history` retry5's row above).
**Cost per 1,000 exported rows: $0.004888 / 20,866.603 = $0.000234 per
1,000 rows** — but this number is nearly meaningless as a marginal rate: the
task's cost is a fixed ~151 seconds of `large`-profile compute *regardless*
of whether the underlying silver dataset has 1 row or 20 million, because
`gold_refresh` always rebuilds and re-exports the complete current table set
in one pass. **The correct unit-economics framing for `gold_refresh` is "≈$0.005
per invocation," not "≈$0.0002 per 1,000 rows"** — the latter number would
imply cost scales with data volume, which this evidence directly
contradicts (compare `ticket07-profile-gold-refresh-1785757940`, an earlier
`gold_refresh` execution also on `large`, whose Ticket 02-documented 169.12s
lifetime included a since-removed 60.65s no-op silver-publish step — even
that heavier historical shape cost only $0.00547, not meaningfully more
despite touching the same ~20M-row snapshot).

**Records/sec:** not a meaningful metric for this workflow — it re-exports
an existing snapshot rather than producing new records at a rate.

**Failure rate (30-day, Ticket 11):** 4 runs, 4/4 succeeded (100%) — the only
workflow in the portfolio with a perfect 30-day success record.

---

### `seed_universe` — a second fixed-cost, low-volume example, with a resolved 26-vs-current caveat

Execution `399ec351-8a18-4934-9b58-46e847d69afb`, **SUCCEEDED**,
2026-07-31T14:58:18→15:04:58 (-04:00) = **6m40s**, 1 parent task (385s
billed, `medium`, **$0.006231**). State transitions: 2 (1+1), $0.00005.

This specific execution predates `SNOWFLAKE_REFRESH_STATUS`'s 2026-08-07
earliest row, so its own row count is not independently bound. However, this
pass's fresh query (above, under `load_history`) newly confirms
**`seed_universe`'s row count is stably 10,398 across four separate,
genuinely Step-Functions-bound executions** spanning 2026-08-10 to
2026-08-10 (`ticket42-task35-fulluniverse-retry3/4/5`, `ticket05-verify2`) —
all embedded inside `load_history`'s `SeedUniverse` sub-stage, all landing
exactly 10,398 rows/1 table. This resolves gate 3's earlier caveat that its
only row-count-bound `seed_universe` example (`c8abbf66-...`) bypassed Step
Functions entirely — genuine SFN-bound examples now exist, at $0.008545 per
invocation (the `large`-profile `seed-universe` sub-task inside
`load_history` retry5, 264s billed) for the same 10,398-row output. **Cost
per 1,000 exported rows: $0.008545 / 10.398 = $0.822 per 1,000 rows** — again
dominated by fixed per-invocation cost against a small, largely-static
ticker universe, not a volume-scaling rate.

**Failure rate (30-day, Ticket 11):** 1 run, 1/1 succeeded.

---

### `targeted_resync` — sampled execution is non-representative; use the aggregate

Execution `ticket84-leaseverify-deferred-msft-1785840639`, **SUCCEEDED**,
2026-08-04T06:50:41→06:52:18 (-04:00) = **1m37s**, but its execution history
shows only **1 parent task** (`acquire-sec-fetch-lease`, 86s billed, `large`,
**$0.002784**) — this run-name (`leaseverify-deferred`) indicates it was a
deliberate lease-contention smoke test that short-circuited before the
`targeted-resync` command itself ran, not a representative production
resync. State transitions: 5 (1+4), $0.000125.

**This sample should not be read as "targeted_resync costs $0.0028."**
Ticket 11's 30-day aggregate is the better representative figure for this
workflow: success p50/p95 **1.6m/1.6m**, unsuccessful p50/p95
**20.2m/24.4m**, 4 runs (1 succeeded / 3 failed / 0 aborted, 25%
terminal-succeeded). Records: not captured this pass for any
`targeted_resync` execution — flagged as an evidence gap rather than
estimated from the non-representative sample above.

---

### `bootstrap_full`, `full_reconcile`, `load_daily_form_index_for_date`, `catch_up_daily_form_index` — zero executions

All four confirmed zero executions in Ticket 11's 30-day window and in this
pass's fresh `list-executions` re-check (2026-08-12): `[]` for each. **$0
Fargate cost, $0 state-transition cost, no records — genuinely zero, not
unreconstructable**, because nothing has run to reconstruct. See
§Zero-execution workflows for the full list and its own caveats.

---

## Standalone MDM utility workflows

Per the ticket's own instruction, several of these are explicitly
**non-record-based** — connectivity/verification utilities whose value is a
control-plane signal, not a record volume. Reusing Ticket 11's own
classification (`mdm_check_connectivity`, `mdm_counts`: "audit/operator...
no durable downstream data consumer"; `mdm_verify_graph`: the ticket's own
named example) rather than re-deriving it.

| Workflow | Sample execution | Profile | Billed-sec | Cost | Transitions | Record-based denominator |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `mdm_migrate` | `aws-mdm-e2e-1786310173-migrate` | mdm-small | 72 | $0.000494 | 2 ($0.00005) | **Not meaningful** — schema migration, no row count |
| `mdm_check_connectivity` | `postcutover-connectivity-1784494654` | mdm-small | 60 | $0.000411 | 2 ($0.00005) | **Not meaningful** — connectivity probe (Ticket 11's own classification) |
| `mdm_run` | `aws-mdm-e2e-1786310173-run` (`--limit 5`, smoke test) | mdm-medium | 102 | $0.001651 | 3 ($0.000075) | **Not meaningful for this sample** — `--limit 5` bounded smoke test; a full unbounded `mdm run` (see `bronze_seed_silver_gold`'s 44,227s/$0.7158 embedded example above) is genuinely record-volume-scaling, just not this standalone workflow's sampled execution |
| `mdm_backfill_relationships` (bounded smoke test) | `aws-mdm-e2e-1786310173-backfill` (`--limit 100`) | mdm-medium | 467 | $0.007558 | 5 ($0.000125) | **0 records inserted** (Ticket 12 §6: all 11 relationship types already at/above their per-type target, a pure no-op verification pass) — cost-per-record is undefined for this sample, not "cheap" |
| `mdm_backfill_relationships` (real, non-zero-insert, 17 days old) | `edge09-employed-by-postfix3-1785108623` | mdm-medium | 1,987 | $0.032158 | — | Row count not recoverable (CloudWatch retention gone at 17 days) — cost is exact via Step Functions' 90-day history, insert count is not |
| `mdm_backfill_relationships` (real, `INSTITUTIONAL_HOLDS`, 17 days old) | `edge11-institutional-holds-fullrun-1785098441` | mdm-medium | 5,950 | $0.096295 | — | Same gap — cost exact, insert count not recoverable. Live `MDM_RELATIONSHIP_INSTANCE` count query (`CREATED_AT` in this execution's window) returns **0**, but this is expected, not evidence of a no-op: the current Snowflake `MDM` schema was recreated 2026-08-09 (CLAUDE.md's documented "MDM Snowflake mirror schema lost on cutover" incident) — no row from a 2026-07-26 execution can exist in the post-cutover table regardless of whether the original backfill worked |
| `mdm_sync_graph` | `aws-mdm-e2e-1786310173-sync` (`--limit 100`) | mdm-medium | 73 | $0.001181 | 6 ($0.00015) | **100 nodes + 100 edges synced** (hit the `--limit` ceiling exactly, Ticket 12 §7a) → **$0.01181 per 1,000 nodes synced, $0.01181 per 1,000 edges synced** |
| `mdm_verify_graph` | `aws-mdm-e2e-1786310173-verify` | mdm-small | 259 | $0.001776 | 2 ($0.00005) | **Not meaningful** — this ticket's own named example of a verification utility |
| `mdm_counts` | `aws-mdm-e2e-1786310173-counts` | mdm-small | 60 | $0.000411 | 2 ($0.00005) | **Not meaningful** — read-only count/report |
| `mdm_seed_universe` | — | — | — | $0 | — | Zero executions (see below) |
| `mdm_seed_from_silver` | — | — | — | $0 | — | Zero executions, machine now deleted (see below) |

All figures cross-checked against Ticket 02's already-published bounded-MDM-chain
total ($0.0131 for the six `aws-mdm-e2e-1786310173-*` commands excluding
`mdm export`) — summing this table's `migrate`+`run`+`backfill`(bounded)+
`sync`+`verify`+`counts` rows gives $0.000494+$0.001651+$0.007558+$0.001181+
$0.001776+$0.000411 = **$0.013071**, matching Ticket 02's $0.0131 to 4
significant figures.

**Failure rate (30-day, Ticket 11):** `mdm-run` 6 runs (3/3/0, 50%);
`mdm-backfill-relationships` 13 runs (9/4/0, 69%); `mdm-sync-graph` 6 runs
(4/2/0, 67%); `mdm-verify-graph` 4 runs (1/3/0, 25% — the lowest of the
bounded utilities, consistent with verification catching real parity issues
rather than passing trivially); `mdm-check-connectivity`/`mdm-migrate`/
`mdm-counts` all 100% (3/3, 3/3, 2/2) — these three are simple, low-variance
control-plane calls.

---

## Zero-execution workflows

9 of the 26 workflows in Ticket 11's inventory had zero executions in the
30-day window; re-checked live this pass (`aws stepfunctions list-executions`,
2026-08-12) with one material update:

| Workflow | Status this pass | Note |
| --- | --- | --- |
| `bootstrap_full` | 0 executions, machine live | Genuinely $0 — never run |
| `catch_up_daily_form_index` | 0 executions, machine live | Genuinely $0 — never run |
| `full_reconcile` | 0 executions, machine live | Genuinely $0 — never run |
| `load_daily_form_index_for_date` | 0 executions, machine live | Genuinely $0 — never run |
| `mdm_gold` | 0 executions, machine live | Genuinely $0 — never run |
| `mdm_seed_universe` | 0 executions, machine live | Genuinely $0 — never run |
| `silver_mdm_gold` | 0 executions, machine live | Genuinely $0 — never run; its `BatchSilver` Map's cost shape is only known via the structurally-identical but distinct `bronze_seed_silver_gold` proxy above (Ticket 12's own framing, reused, not re-derived) |
| `bootstrap_batched` | **Machine deleted** (`list-state-machines` confirms it no longer exists) | Cost is now **$0 by deletion**, a different portfolio fact than "$0 by dormancy" — per the gate 1 addendum, superseded by PR #398's state-machine consolidation, zero executions ever even before deletion |
| `mdm_seed_from_silver` | **Machine deleted** | Same as above — $0 by deletion, zero executions ever |

**Portfolio total for these 9: $0 Fargate, $0 state transitions, no records
— by construction, not estimation.**

---

## Scope note: 26-workflow inventory vs. current live count

Per this ticket's instruction, the above covers all 26 workflows in Ticket
11's inventory. A fresh `aws stepfunctions list-state-machines` this pass
(2026-08-12) returns **24** live `edgartools-prod-*` machines, not 26 — the
gate 1 addendum's finding, re-confirmed directly here:
`bootstrap_batched` and `mdm_seed_from_silver` (both zero-execution, $0 cost
regardless) were deleted by the state-machine-consolidation commit
(PR #398/#399, `bb05b885`, 2026-08-10). A new machine,
`edgartools-prod-mdm-utility`, now exists (consolidating 7 of the frozen MDM
machines' functionality — `mdm-run`, `-backfill-relationships`,
`-check-connectivity`, `-counts`, `-migrate`, `-sync-graph`, `-verify-graph`
per the gate 1 addendum's own finding) but is **outside Ticket 11's 26-item
inventory and has zero executions** — not costed here, flagged for whoever
picks up Ticket 14's portfolio decision to include in the next inventory
pass.

---

## Cost-vs-completion-time ranking across all 26 workflows

**One genuine frontier exists in this evidence** — multiple real,
measured configurations of the *same* workload (Ticket 02's `BatchSilver`
profile/concurrency comparison, reused directly, not re-derived):

| Configuration | Duration | Cost | Completeness |
| --- | --- | --- | --- |
| `medium`/concurrency 20 | 52m06s | $0.9912 | **680/680 complete** |
| `large`/concurrency 16 | 22m04s (before failure) | $0.6794 (partial) | **216/680, then a hard ECS vCPU-quota failure** — faster and cheaper *only if you don't count the incomplete 464 items* |
| `large`/concurrency 4 | 1h32m56s | not fully computed (partial) | 240/680, operator-aborted |

This is the ticket's own named case: a configuration that looks faster and
cheaper (`large`/16, 22 minutes, $0.68) is invalid because it never produced
a complete output — the account's 30-vCPU concurrent quota rejected the 17th
task's 32-vCPU cumulative request. `medium`/20 is the only complete,
valid point on this frontier.

**Every other row below is one observed cost/duration pair per workflow, not
multiple configurations of the same workload — presented as a ranking, not a
frontier**, per this pass's own scope (manufacturing untested configurations
was explicitly avoided):

| Workflow | Cost (sampled exec.) | Duration (sampled exec.) | $/hour | Completeness this run |
| --- | ---: | ---: | ---: | --- |
| `generation_build` | $0.001646 | 6m38s | $0.0149 | Complete (only-ever run, succeeded) |
| `gold_refresh` | $0.004888 | 2m42s | $0.1086 | Complete, 20.87M rows/23 tables |
| `seed_universe` (standalone) | $0.006231 | 6m40s | $0.0561 | Complete (row count not bound to this exact execution) |
| `mdm_sync_graph` | $0.001181 | 1m30s | $0.0472 | Complete, 100/100 nodes+edges (limit-bounded) |
| `mdm_verify_graph` | $0.001776 | 4m32s | $0.0235 | Complete, verification-only |
| `mdm_backfill_relationships` (real insert) | $0.032158–$0.096295 | 33m07s–99m10s | $0.0583–$0.0582 | Complete; insert count not recoverable |
| `targeted_resync` (non-representative sample) | $0.002784 | 1m37s | $0.1032 | Incomplete signal — see caveat above; use 30-day p50 1.6m instead |
| `residual_holds_graph` (attempt 2) | $0.141709 | 1h23m48s | $0.1015 | 8/9 stages complete, verification failed (no `Catch`) |
| `bootstrap` | $0.381558 | 4h09m43s | $0.0917 | Complete, masked `MdmVerify` failure (`Catch`) |
| `daily_incremental` | $0.385757 | 4h50m41s | $0.0797 | Complete, masked `MdmVerify` failure (`Catch`); **dormant 8 days as of capture** |
| `bronze_seed_silver_gold` (full-MDM-run instance) | $0.729996 | 13h38m43s | $0.0535 | **Incomplete — failed at `mdm export`, zero Snowflake commit** |
| `bronze_seed_silver_gold` (`StrictBatchSilver` instance) | $0.9912 | 52m06s | $1.1417 | Complete for its own scope (680/680 silver batches); pipeline continuation not evidenced in this instance |
| `load_history` (retry5) | $2.07–$3.39 | 30h23m14s | $0.068–$0.112 | **Contradictory by capture time** — 20.97M gold rows committed and confirmed durable (chain G binding), but the workflow's own terminal status is `FAILED`, and the underlying Snowflake tracking row itself shows `running` as of this pass's live re-query (differing from Ticket 12/gate 3's same-day `succeeded` snapshot) |

**Reading this ranking, not a frontier:** cost per hour of wall-clock time is
not itself informative here — `bronze_seed_silver_gold`'s `StrictBatchSilver`
instance has the highest $/hour ($1.14) precisely *because* it is short and
uses `MaxConcurrency:20` (20 tasks running simultaneously costs more per
wall-clock hour than one task running alone, by design — that is the whole
point of paying for concurrency to finish faster). The workflows worth
comparing directly are the ones producing the same kind of output:
`load_history` and `bronze_seed_silver_gold`'s `StrictBatchSilver` both
produce silver rows, at $9.46/1,000 and $0.787/1,000 respectively — a
12× difference explained entirely by network I/O versus reprocessing, not by
task profile.

---

## Limitations — evidence that could not be reconstructed, stated explicitly

1. **Stage 1B's (`load_history`) per-child Fargate cost** — bounded to a
   $0.01–$1.33 range, not point-measured; would require locating up to 6
   individual child execution ARNs via the same wall-clock-window workaround
   Ticket 12 used for logs (not attempted this pass, given the advisor
   guidance to bound rather than exhaustively pursue this exact gap).
2. **`ownership_mdm_gold`'s Fargate cost** — the one execution in the 30-day
   window was aborted before any `TaskSucceeded`/`TaskFailed` event recorded
   an ECS result; genuinely unrecoverable from Step Functions history, and
   the underlying ECS task (18 days old) is too old for `describe-tasks`.
3. **`bootstrap`'s, `bronze_seed_silver_gold`'s (full-MDM-run instance),
   `daily_incremental`'s, and `seed_universe`'s (standalone) record counts**
   — all four sampled executions predate `SNOWFLAKE_REFRESH_STATUS`'s
   2026-08-07 earliest row (a table with only 8 total rows ever, queried
   live this pass, not previously enumerated by Ticket 11 or 12). This is a
   tracking-table-coverage gap, not a data-loss gap — the underlying
   Snowflake writes may well have succeeded; there is simply no per-run
   ledger row old enough to bind them to.
4. **`edge09-employed-by-postfix3-1785108623`'s and
   `edge11-institutional-holds-fullrun-1785098441`'s inserted-row counts** —
   both executions' Fargate cost is exact (Step Functions' 90-day history
   covers them), but their CloudWatch structured logs (the source of
   per-type insert counts, per Ticket 12 §6) are gone at 17 days, past the
   7-day retention window.
5. **`generation_build`'s `BuildPartitions` Map child-level cost and record
   counts** — the parent execution is within Step Functions' 90-day
   history, but this pass did not pursue the individual 17 partition-task
   child executions; flagged as available-but-unpursued rather than
   genuinely gone (distinct from #4 above, which is truly gone).
6. **`residual_holds_graph`'s candidate output** — the generation it built
   predates the current Snowflake graph schema (recreated 2026-08-07/09) and
   no longer exists to query; only a later, separately-sourced manual
   sync/verify figure (193,323 nodes/166,067 edges, from CLAUDE.md) exists as
   context, not as this execution's own bound output.
7. **`load_history` retry5's `SNOWFLAKE_REFRESH_STATUS` row status
   discrepancy** (`running` here vs. `succeeded` in Ticket 12/gate 3's
   same-day capture) — not resolved this pass; both are real, correctly
   captured snapshots of a mutable field, presented as an open, unresolved
   observation rather than a reconciled fact.
8. **Portfolio-wide CloudWatch logging cost** is a current-snapshot bound
   (≈$0.30 for the trailing week, ≈$1.29/month projected), not a
   per-execution or per-workflow attribution — the same 7-day retention gap
   that blocks record-level log evidence elsewhere in this workstream also
   blocks attributing log volume to individual executions older than 7 days.
