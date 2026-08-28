# Measure Every Loop and Record Funnel

Type: research
Status: resolved
Blocked by: 01

## Question

For every Step Functions Map/Distributed Map and every material internal CLI
loop, what is the loop item, item source, batch or window size, item count per
execution, records selected and attempted per item, records committed and
exported, idempotent skips, rejects, retries, duplicates, duration, peak
CPU/memory, and effective concurrency?

Cover at least CIK batches, CIK windows, filing/accession loops, relationship
types, generation partitions, graph-sync batches, and MDM limits. Reconcile
Step Functions history, Map Run metrics, ECS task metrics, logs, S3 manifests,
run summaries, and durable outcome ledgers. Explicitly distinguish a loop item
from the number of records produced by that item so `records per loop` cannot
be mistaken for `Map item count`.

## Answer

Full inventory, one section per loop type, every claim cited to an exact AWS
CLI call/resource/timestamp or file:line, is in
[`loop-inventory-and-funnel-2026-08-12.md`](../research/loop-inventory-and-funnel-2026-08-12.md).
Prefers real recent executions over source-code estimates throughout; where
no live execution exists within CloudWatch's 7-day retention, says so
explicitly rather than substituting a guess.

**Item vs. record counts, by loop type (item count → real record volume,
same execution unless noted):**

| Loop type | Item count | Records | Multiplier |
|---|---|---|---|
| CIK windows (`load_history`) | 53 windows | 26,300 CIKs (Stage0) / 5,300 CIKs (WindowedBootstrap) | up to ~500x |
| Filing/accession loop (inside `WindowedBootstrap`) | n/a (Python loop, not a Map) | 55,269 accessions attempted → 201,154 silver rows written | — |
| Stage 1B fundamentals (3 Maps) | 53 windows each | Failed at item 1, all three — Map-level `FAILED` but pipeline fell through to `GoldRefresh` anyway (Catch, AD-13) | n/a |
| CIK batches (`bronze_seed_silver_gold`'s `StrictBatchSilver`) | 680 batches | 67,807 CIKs, 1,259,036 silver rows written | ~1,850x |
| `Stage0CompanyIdentityBounded` (`daily_incremental`) | 3 batches (last known) | Not recoverable — execution outside 7-day retention | — |
| Relationship types (`mdm backfill-relationships`) | 11 types | 0 to 563,631 rows per type (`MANAGES_FUND` dominant) | >20x range across types |
| Generation partitions (`generation_build`) | 17 partitions | Not recoverable — only-ever execution is 21 days old | — |
| Graph-sync (`mdm sync-graph`) | n/a (single command, `--limit`-bounded) | 100/100 nodes/edges synced (hit the limit exactly) | — |

**Findings beyond the inventory itself, load-bearing for later tickets:**

1. **A masked-success instance, independently found (not a repeat of Gate
   5's `MdmVerify` finding):** `ticket42-task35-fulluniverse-retry5-1786380966`
   has overall Step Functions status `FAILED`, yet its `GoldRefresh` step
   durably committed ~21M rows to Snowflake (`SNOWFLAKE_REFRESH_STATUS`:
   `succeeded`, `SOURCE_ROW_COUNT: 20,966,689`) under the same `run_id`.
   Any tool inferring "records committed = 0" from `FAILED` status alone is
   wrong for this execution. Directly relevant to Tickets 13 and 17, which
   would otherwise build unit-economics/telemetry on Step Functions terminal
   status as ground truth.
2. **Distributed Map child executions get UUID `run_id`s uncorrelated to the
   parent execution name** — `$$.Execution.Name` inside a `DISTRIBUTED`
   Map's `ItemProcessor` resolves to the child's own generated name, not the
   parent's. No CloudWatch Logs Insights query can cleanly attribute
   per-window/per-batch log lines to one parent execution without a
   wall-clock-window heuristic. The single biggest instrumentation gap
   found this pass.
3. **`daily_incremental` has had zero executions in the trailing 8 days** as
   of this capture, despite being documented as the ongoing production
   cadence. **`silver_mdm_gold` has zero executions ever** (re-confirms
   Gate 4). **`generation_build` has exactly one execution ever**, 21 days
   old.
4. **CLAUDE.md's "Phased Pipeline" section is stale for `load_history`**:
   `Stage0CompanyIdentity` was removed (folded into `WindowedBootstrap`) by
   PR #396 (commit `da8ccb65`, 2026-08-10T18:35:39-04:00). This ticket's own
   primary evidence execution ran its `Stage0CompanyIdentity` pass 3.5 hours
   *before* that commit merged — real production evidence of a stage that no
   longer exists in current source. Out of this map's scope to fix (doc
   accuracy, not cost/sizing policy) — flagged for whoever next touches that
   doc.
5. **Smaller open question, not root-caused:** an `mdm backfill-relationships
   --limit 100` invocation emitted `target: 5` on every relationship type's
   progress event — `--limit` and `derive_relationships`'s internal
   `target_per_type` are evidently not the same value. Not resolved this
   pass.

None of these findings block Ticket 12 itself; they're carried forward as
evidence for Tickets 13, 15, 16, and 17, all of which are blocked on this
ticket and reference "loop item"/"record funnel" concepts directly.
