# Build Workflow Unit Economics

Type: research
Status: resolved
Blocked by: 02, 11, 12

## Question

How quickly does each production workflow produce a complete validated output,
what does it cost per successful execution, per 1,000 committed records, and
per 1,000 exported records, and what useful output or operator capability does
that time and spend purchase?

Attribute Fargate vCPU-seconds and GB-seconds by stage and profile, Step
Functions state transitions and Map Runs, retries and duplicate work, and
material logging or storage overhead. Report end-to-end and stage duration,
critical-path wait, records per second, failure rate, freshness contribution,
and output completeness beside cost. Build the cost-versus-completion-time
frontier so faster valid configurations are visible even when they cost more.
Separate fixed orchestration cost from record-volume-dependent work, and mark
workflows whose record-based denominator is not meaningful, such as
connectivity or verification utilities.

## Answer

Full workflow-by-workflow costing, every dollar figure derived from exact
`get-execution-history` ECS billing fields (not estimated), with pricing
basis and method fully shown, is in
[`workflow-unit-economics-2026-08-12.md`](../research/workflow-unit-economics-2026-08-12.md).
Covers all 26 workflows from Ticket 11's inventory: 17 costed from a real
execution, 9 genuinely zero (never run, 2 of those now machine-deleted). Step
Functions state-transition cost and CloudWatch logging overhead are both
confirmed immaterial to this portfolio (bounded and shown, not assumed).

**Fixed-cost vs. record-volume-scaling workflows, cleanly separated as
asked:**

| Workflow | Shape | Evidence |
|---|---|---|
| `gold_refresh` | Fixed ~$0.005/invocation regardless of snapshot size | Re-exports 20.87M rows in 151s billed on `large`; an earlier, heavier historical shape cost the same |
| `seed_universe` | Fixed ~$0.008545/invocation | 10,398 rows, static ticker universe, 4 independent executions confirm the same row count |
| `mdm_verify_graph`/`mdm_check_connectivity`/`mdm_counts`/`mdm_migrate` | Not record-based at all | Control-plane signal, no downstream row count (ticket's own named example, confirmed) |
| `load_history`'s `WindowedBootstrap` | Scales with SEC network I/O, not task profile | $9.46/1,000 silver rows, rate-limited at `MaxConcurrency:1`, 3.85 rows/sec |
| `bronze_seed_silver_gold`'s `StrictBatchSilver` | Scales with reprocessing volume, cheap because zero network calls | $0.787/1,000 silver rows at `MaxConcurrency:20` — **12× cheaper per row** than `load_history`'s equivalent stage, 402.8 rows/sec (~105×) |

**The one genuine cost-vs-completion-time frontier found** (Ticket 02's
`BatchSilver` profile/concurrency comparison, reused): `medium`/concurrency
20 (52m06s, $0.9912, 680/680 complete) is the only valid point — `large`/16
looks faster and cheaper (22m, $0.68) but is invalid because it hit a hard
ECS vCPU-quota failure at 216/680 items and never completed. Every other
workflow contributes one observed cost/duration pair, not multiple tested
configurations, so those are reported as a ranking, not a frontier — building
more frontier points would mean deliberately re-running workflows at
different profiles, out of this ticket's read-only scope.

**Findings beyond costing itself, load-bearing for later tickets:**

1. **A sharper, independently-derived root cause for `load_history` retry5's
   masked success** (Ticket 12 found the execution: `FAILED` status, ~21M
   rows committed. This pass traced *why*, event-by-event): the `FAILED`
   terminus is attributable specifically to `WriteRunSummary` — a pure
   bookkeeping step with **no `Catch`** — failing 4 times *after* the real
   output (20,966,689 gold rows) was already durably committed via a
   `Catch`-protected `MdmVerify`→`GoldRefresh` path. An operator reading only
   terminal status would misattribute both *what* happened (zero output) and
   *why* (a data-producing failure, when it was actually a bookkeeping
   failure downstream of success).
2. **A live, unresolved data-consistency observation**: this same
   execution's `SNOWFLAKE_REFRESH_STATUS` row now reads `STATUS: running`,
   contradicting Ticket 12/gate 3's same-day capture of `STATUS: succeeded`
   for the identical `RUN_ID`. Not reconciled this pass — flagged as open.
3. **A genuine, unmasked zero-commit failure**, the mirror image of finding
   1: `bronze_seed_silver_gold`'s full-MDM-run instance spent $0.73 (mostly a
   12h17m `mdm run`) then failed 4× at `mdm export` with **no `Catch`** —
   confirmed via a fresh Snowflake query that no manifest row exists at all
   for that run. Real compute cost, zero downstream value, no ambiguity.
4. **Portfolio orchestration overhead is immaterial everywhere checked**:
   Step Functions state transitions cap at ~$0.034 even for the most
   Map-heavy single execution in the portfolio (3-4 orders of magnitude below
   Fargate compute cost); CloudWatch logging is ≈$1.29/month projected
   against a portfolio whose single costliest traced execution alone exceeds
   $2.
5. **The live inventory has already drifted from Ticket 11's 26-workflow
   baseline**: `bootstrap_batched` and `mdm_seed_from_silver` are now
   deleted (PR #398/#399, consolidation); a new `edgartools-prod-mdm-utility`
   machine exists, outside Ticket 11's inventory, zero executions, not
   costed here — flagged for whoever next revises the workflow-portfolio
   decision.

**Evidence genuinely unreconstructable, stated rather than estimated:**
`load_history`'s Stage 1B per-child cost (bounded $0.01–$1.33, only ~2 of up
to 159 possible children ever started); `ownership_mdm_gold`'s Fargate cost
(aborted before any ECS result was recorded); record counts for `bootstrap`,
`daily_incremental`, `bronze_seed_silver_gold`'s full-MDM instance, and
standalone `seed_universe` (all predate `SNOWFLAKE_REFRESH_STATUS`'s
2026-08-07 earliest row); insert counts for two real relationship backfills
whose cost is exact (90-day Step Functions retention) but whose CloudWatch
logs are gone (7-day retention, 17-day-old executions).
