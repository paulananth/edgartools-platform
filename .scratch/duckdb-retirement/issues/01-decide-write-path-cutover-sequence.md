# Decide the Production Write-Path Cutover Sequence

Type: grilling
Status: resolved
Blocked by: 02 (resolved), 03 (resolved), 04 (resolved), 08 (resolved)

## Question

The closed silver-snowflake-migration map's Ticket 02 decided the write
path dual-writes today: parse fans out in-process to both DuckDB silver
and the Snowflake landing zone in parallel. This map's destination is
Snowflake-only — DuckDB stops being written entirely. That can only happen
safely once every reader currently depending on DuckDB has moved off it:
MDM ([Ticket 02](02-decide-mdm-reader-replacement-mechanics.md)), gold
([Ticket 03](03-decide-gold-builder-retirement-mechanics.md)), and
`bootstrap-batch` ([Ticket 04](04-decide-bootstrap-batch-sharding-fate.md))
— hence this ticket is blocked by all three.

Decide, once those are settled: the actual mechanics of turning off the
DuckDB write in `_run_submissions_bronze_then_silver`/
`_apply_submission_snapshot_to_silver` (`warehouse_orchestrator.py:3085`/
`:4820`) — a flag-gated transition (both writes continue for a defined
period as a safety net) or an atomic code change once all three consumers
have confirmed their cutover? What happens to an `load_history`/
`daily_incremental` execution that's *mid-flight* across the cutover
boundary (a window that started under dual-write, finishes after DuckDB
writes are removed)? What's the rollback story if a production issue
surfaces post-cutover, given DuckDB fully leaves the codebase per this
map's scope — is rollback "revert the commit and redeploy" (no live
toggle), and is that an acceptable answer given "the whole platform's
silver data" is what's at stake? Finally, decide disposition of the
existing `s3://edgartools-prod-warehouse-*/warehouse/silver/sec/
silver.duckdb` file and its shards once writes stop — deleted immediately,
archived for a retention period, or left in place under an S3 lifecycle
rule (matching this repo's existing precedent, CLAUDE.md's "S3 lifecycle
rule for warehouse/silver/").

## Deliverable

A decided cutover mechanism (flag-gated vs. atomic), an answer for
mid-flight executions crossing the boundary, an explicit rollback story,
and a decided disposition for the existing DuckDB files in S3.

## Answer

**Grounding, checked directly:** `register_task_definition()`
(`deploy-aws-application.sh:1179-1197`) calls `ecs register-task-definition`
and captures `taskDefinition.taskDefinitionArn` — the **specific-revision**
ARN (`.../task-definition/name:N`), not a floating family reference. That
exact ARN is baked directly into the Step Functions state machine JSON
(`"TaskDefinition": task_def_arn`, ~10 call sites) at every deploy. Combined
with Step Functions' own documented behavior — an execution runs against
the state machine definition snapshot active when it *started*, unaffected
by a later `UpdateStateMachine` call — this means an already-running
`load_history`/`daily_incremental` execution keeps launching ECS tasks on
the **old** image/revision for its entire lifecycle, even for windows it
reaches after a redeploy happens concurrently. This isolation already
exists; nothing new has to be built for it.

- **Atomic code change, no flag-gated transition window.** Consistent with
  this map's own established precedent (Ticket 02 and Ticket 04 both chose
  hard cutover over a toggle for the same reason: a flag is state that
  itself needs testing and eventual removal). The mid-flight risk a flag
  would exist to protect against is already covered for free by the
  pinned-task-definition-ARN + execution-snapshot behavior above — no
  in-flight execution can straddle old-write/new-write behavior
  mid-stream, because it never sees the new code at all until it starts a
  fresh execution.
- **Mid-flight executions need no special handling** — they simply
  complete under the old code path (DuckDB-writing) they started with; the
  first execution to observe the new behavior is the first one *started*
  after the redeploy, not any window within an execution already underway.
- **Rollback is all-or-nothing across the whole stack, not the write path
  alone — recorded explicitly because the narrower version is a real
  trap.** MDM (Ticket 02) and gold (Ticket 03) both chose hard cutover with
  no DuckDB fallback kept live in their read paths. If a post-cutover
  issue prompted rolling back *only* the write path (redeploying old code
  that resumes writing DuckDB) while MDM/gold still read exclusively from
  Snowflake, the landing zone and bookkeeping store would simply stop
  receiving fresh writes — MDM/gold wouldn't error, they'd silently go
  stale. "Revert the commit(s) and redeploy" is the rollback story, exactly
  as this repo already practices (this session's own rollback-capture step
  before this map's earlier deploys), but it must mean reverting the write
  path together with MDM's and gold's reader cutovers as one unit, not
  independently.
- **Added 2026-08-28, per [Ticket 09](09-account-for-silver-acceptance-in-write-path-cutover.md):**
  the atomic bundle above also includes the acquisition family's
  `*_silver_acceptance.py` modules — `edgar_warehouse/acquisition/
  silver_acceptance.py` (filing_artifact) plus its four siblings
  (`reference_catalog_`, `company_facts_`, `submissions_`,
  `adv_bulk_dataset_silver_acceptance.py`) — all of which take
  `SilverDatabase` (DuckDB) as a direct, hard-coupled parameter and must be
  ported to the Snowflake target in the same atomic change as the write path
  itself, not sequenced separately. These postdate this ticket's original
  2026-08-16 answer (created 2026-08-23 to 2026-08-25 by the
  change-propagation map) and were never accounted for here until Ticket 09
  closed the gap.
- **DuckDB file disposition: bounded retention, then archive/delete** —
  extends this repo's existing precedent
  (`expire-noncurrent-silver-canonical-versions`,
  `infra/terraform/modules/storage_buckets/main.tf:150-161`, ecs-cost-sizing
  Ticket 22) rather than inventing a new pattern. That existing rule only
  ever expires *noncurrent* versions and deliberately never touches the
  live current version — once nothing publishes to `warehouse/silver/`
  anymore, the current `silver.duckdb` + shard files freeze permanently
  under that rule with no further action. A companion rule transitions the
  final current version to Glacier (or expires it outright) after a fixed
  window — exact retention length (30-90 days, per the earlier framing) is
  an implementation-time call, not pinned here — giving a real
  rollback-forensics aid through the highest-risk early post-cutover period
  without carrying ~1.34TB indefinitely.
