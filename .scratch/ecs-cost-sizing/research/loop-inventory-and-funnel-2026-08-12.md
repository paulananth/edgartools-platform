# Ticket 12 — Loop and Record-Funnel Inventory

Date: 2026-08-12. Scope: every Step Functions Map/Distributed Map and every
material internal CLI loop in the `edgartools-prod` portfolio (account
`690839588395`, region `us-east-1`). All AWS/Snowflake calls in this pass
were read-only (`describe-*`, `list-*`, `get-*`, `SELECT`).

**Governing distinction, held throughout:** *loop item count* (how many
times a Map/for-loop iterates) is never conflated with *records per loop*
(how many underlying rows/accessions/entities that iteration touched). Every
table below carries both, in separate rows, with separate units.

**CloudWatch retention:** `/aws/ecs/edgartools-prod-warehouse` (the single
log group both warehouse and MDM ECS tasks write to, differentiated by
`awslogs-stream-prefix`) has `retentionInDays: 7`
(`aws logs describe-log-groups`, captured 2026-08-12). "Today" for this
pass is 2026-08-12, so only executions starting on/after ~2026-08-05 have
any log-line-level evidence available. Where a loop's most-recent execution
predates that, this is stated explicitly rather than silently substituting
an older run's numbers.

**A traceability gap discovered while building this inventory, load-bearing
for every Distributed Map section below:** inside a Distributed Map
`ItemProcessor` running in `DISTRIBUTED` mode, `$$.Execution.Name` resolves
to the **child execution's own auto-generated name** (a UUID, e.g.
`4b0a1d47-76b1-3544-a503-e332d54d68ce`), **not** the parent execution's
name string. `load_history`'s per-window command passes
`'--run-id', $$.Execution.Name` (`infra/scripts/deploy-aws-application.sh:2442`),
so every per-window/per-batch structured log line carries this
child-generated UUID as `run_id`, never the human-chosen parent execution
name (e.g. `ticket42-task35-fulluniverse-retry5-1786380966`). Verified
directly: a CloudWatch Logs Insights query filtering
`run_id like /ticket42-task35-fulluniverse-retry5/` against the exact
window this execution ran in returned only 11 *top-level* (non-Map) events
(`gold_build_*`, `gold_publish_*`, `gold_refresh_started`,
`sec_fetch_lease_released`, `pipeline_failed`×4, `silver_publish_*`×12) —
zero of the many per-window `bronze_capture_*`/`filing_artifact_pipeline_*`
events, which all carry a distinct UUID `run_id` each instead.
**Consequence:** an operator cannot filter CloudWatch Logs Insights by a
parent execution's name to retrieve that execution's own per-window log
lines. The workaround used throughout this document is to scope every
Logs Insights query to **both** the exact wall-clock start/stop timestamps
of the specific Map run in question (from `describe-map-run`, cross-checked
against `get-execution-history`'s `MapStateEntered`/`MapRunStarted` event
timestamps — not just a loosely-bounded day-level window) **and** the
task family's `@logStream` prefix (e.g. `warehouse-large`). Sections below
that follow this tight two-part scoping get an exact N-of-N match between
the Map's own `itemCounts` and the aggregated log events (§1, §2, §4);
one section (§3's unresolved 5th map run, later identified — see below)
initially did not, and is corrected accordingly.

---

**Full, execution-history-verified map-run attribution for
`ticket42-task35-fulluniverse-retry5-1786380966`** (used throughout §1-3
below), resolved via `aws stepfunctions get-execution-history`, matching
each `MapStateEntered` event's state name and timestamp exactly against
each `describe-map-run` result's `startDate`:

| # | ASL state | Map-run ARN suffix | Window (-04:00) | `itemCounts` |
|---|---|---|---|---|
| 1 | `Stage0CompanyIdentity` | `bf5ed0f3-...:e0cc103d-...` | 13:16:12 → 15:06:30 | 53 succeeded / 0 failed |
| 2 | `WindowedBootstrap` | `b0437a80-...:e06c9699-...` | 15:42:28 → **2026-08-11 06:12:21** (14h30m) | 53 succeeded / 0 failed |
| 3 | `Stage1BEntityFacts` | `656cc278-...:fc8cc63c-...` | 06:12:21 → 10:38:01 | 0 succeeded / 1 failed / 1 aborted / 51 pending |
| 4 | `Stage1BPerFiling` | `853424f5-...:81ad79d3-...` | 10:38:01 → 12:34:37 | 0 succeeded / 1 failed / 1 aborted / 51 pending |
| 5 | `Stage1BThirteenF` | `ae82e7e2-...:a427eb4c-...` | 12:34:37 → 17:35:08 | 0 succeeded / 1 failed / 1 aborted / 51 pending |

**Important, fresh finding this correction surfaced:** row 1
(`Stage0CompanyIdentity`) is a stage that **no longer exists in
`load_history`'s current source** — it was deleted, together with
`ReduceIdentityRefresh`, by PR #396 ("fold Stage0CompanyIdentity into
Stage1's WindowedBootstrap", commit `da8ccb65`,
**2026-08-10T18:35:39-04:00**). This execution's `Stage0CompanyIdentity`
map ran **13:16-15:06 that same day — 3.5 hours before the removal
commit merged.** So this is not stale documentation in the usual sense;
this execution is the last (or one of the last) real production instances
of a stage that was live when it ran and deleted from source hours later.
Root CLAUDE.md's "Phased Pipeline" section (`seed-universe →
mdm-seed-universe → Stage0CompanyIdentity`) describes the pre-#396 shape
and **is stale relative to current HEAD** (verified:
`git log -S"Stage0CompanyIdentity/ReduceIdentityRefresh removed"` →
`da8ccb65`, and `grep -c Stage0CompanyIdentity
infra/scripts/deploy-aws-application.sh` inside `write_load_history_definition`
now returns 0 — folded into `WindowedBootstrap` per that commit's message).
`daily_incremental`'s own separate `Stage0CompanyIdentityBounded` (§5) is
untouched by this removal — different code path, per the same commit's
message.

## 1. CIK windows (`load_history` — `Stage0CompanyIdentity` + `WindowedBootstrap`, both Distributed Maps, same item source)

Both maps in the table above read the identical `cik_windows.jsonl`
manifest (`cik_windows.jsonl` for this execution: 53 lines, 52×500 +
1×300 = 26,300 CIKs, no `total_cik_limit` set — full active/bootstrap_pending
universe) and share the same item shape.

| Dimension | Value | Source |
|---|---|---|
| Loop item | One `{window_offset, window_limit}` pair | `infra/scripts/deploy-aws-application.sh:2461-2466` (`ItemSelector`, current `WindowedBootstrap`; `Stage0CompanyIdentity`'s pre-removal `ItemSelector` was structurally identical per `git show da8ccb65`) |
| Item source | `cik_windows.jsonl`, written by `compute-windows` to `s3://edgartools-prod-bronze-690839588395/warehouse/bronze/reference/cik_universe/runs/<execution-name>/cik_windows.jsonl` | `deploy-aws-application.sh:2450-2457` (`ItemReader`); confirmed live via `aws s3 cp ... cik_windows.jsonl -` → 53 lines |
| Window (batch) size | 500 CIKs/window by default (`$.window_size`, `WindowSizeDefault` Pass state injects 500 when the caller omits it) | `deploy-aws-application.sh:2225-2233` |
| Item count, real execution | **53 windows** for both maps | `cik_windows.jsonl`, tail line `{"window_offset": 26000, "window_limit": 300}` |
| Map concurrency | `MaxConcurrency: 1` (strict, one window at a time — silver/ownership DuckDB consistency) | `deploy-aws-application.sh:2448` |
| Fan-out mechanism | `Mode: DISTRIBUTED`, `ExecutionType: STANDARD` — each window is a separate STANDARD **child execution** | `deploy-aws-application.sh:2469-2471` |
| `Stage0CompanyIdentity` real outcome | **53/53 succeeded**, 13:16:12→15:06:30 (1h50m) | `describe-map-run`, map-run 1 above |
| `WindowedBootstrap` real outcome | **53/53 succeeded**, 15:42:28→06:12:21 next day (**14h30m** — far longer than Stage0's pass over the identical 53 windows) | `describe-map-run`, map-run 2 above |

**Records selected/attempted/committed — `Stage0CompanyIdentity`'s pass**
(exact 53/53 match: query tightly scoped to `13:16:00`–`15:07:00 -04:00`
**and** `@logStream like /warehouse-large/`, both derived from
`describe-map-run`'s own `startDate`/`stopDate`):

**53 `bronze_capture_completed` events (exact match to the Map's 53
succeeded items) → 26,300 CIKs touched (`sum(cik_count)`, exactly equal to
the window sizes' own sum — confirms this stage captured every CIK in
every window), 27,342 raw bronze objects touched, 0 network fetches
(`catalog_network_fetches` — this counter is the submissions-catalog/
company-identity fetch path specifically, not the document-artifact fetch
path measured separately below), 27,342 idempotent cache-skips
(`catalog_silver_skips`) — a full 100% cache hit on this rerun.**

**Records selected/attempted/committed — `WindowedBootstrap`'s pass**
(same tight-scoping method, window `15:42:00`–`06:15:00(+1d) -04:00`,
`@logStream like /warehouse-large/`, exact 53/53 match):

**53 `bronze_capture_completed` events → only 5,300 CIKs touched this time
(100/window — `WindowedBootstrap`'s `bootstrap-next --silver-only` only
needed a much smaller top-up capture, consistent with `Stage0CompanyIdentity`
having just captured the full window moments earlier in the same
execution), 5,601 raw objects, 0 network fetches, 5,601 skips.**

| Task profile / peak resource use | Value | Source |
|---|---|---|
| Task profile | `wh_large_arn` = `edgartools-prod-large` (2048 CPU / 8192 MB, revision :178 current) — both maps run on `large`; moved here 2026-08-10 after a `wh_medium_arn` (4096 MB) OOM on this exact class of run | `deploy-aws-application.sh:2427-2440`; `aws ecs describe-task-definition --task-definition edgartools-prod-large` |
| Peak memory, live (family-level, not per-task — see instrumentation-gap note) | **4,977 MB** `MemoryUtilized` Maximum, `ECS/ContainerInsights`, `TaskDefinitionFamily=edgartools-prod-large`, 2026-08-10→08-11 (spans both maps above plus any other concurrently-running `large`-family task in the account during that window) | `aws cloudwatch get-metric-statistics --namespace ECS/ContainerInsights --metric-name MemoryUtilized --dimensions ClusterName=edgartools-prod-warehouse,TaskDefinitionFamily=edgartools-prod-large` |
| Peak CPU, live (family-level) | **1,195%** `CpuUtilized` Maximum — this figure sums/maxes across every concurrently-running task in the family, not one task in isolation; not a single-task peak | same metric namespace, `CpuUtilized` |

**Item vs. record distinction, explicit:** 53 is each Map's *item count*
(same 53 for both `Stage0CompanyIdentity` and `WindowedBootstrap` — they
share an item source). 26,300 vs. 5,300 CIKs are *records processed by
those items* for the two different maps in the *same execution*, over the
*same 53 windows* — proof by itself that item count alone says nothing
about record volume, even across two maps with identical item counts.

---

## 2. Filing/accession loop (inside `WindowedBootstrap` — `fetch_filing_artifacts` / `filing_artifact_pipeline`)

Not a Step Functions Map — a Python loop inside `WindowedBootstrap`'s
per-window `bootstrap-next --silver-only --artifact-policy all_attachments`
ECS task (`edgar_warehouse/bronze_filing_artifacts.py`), bounded by
`WAREHOUSE_ARTIFACT_FETCH_CONCURRENCY` (in-task `ThreadPoolExecutor`,
default 5 per CLAUDE.md's Phased Pipeline section — not independently
re-verified this pass). `Stage0CompanyIdentity` does not run this loop at
all (it only does company-identity/submissions capture, per §1's `0`
`filing_artifact_pipeline_*` events in that stage's own window).

| Dimension | Value | Source |
|---|---|---|
| Loop item | One accession (SEC filing) | `edgar_warehouse/bronze_filing_artifacts.py:192-266` (`network_fetches` counter, per-accession) |
| Item source | Accessions selected from the window's CIK list via configured-form selection, intersected with the artifact policy (`all_attachments`/`skip`) | CLAUDE.md "Artifact-throttle 5-whys" note; not re-derived from source this pass |
| Records selected/attempted, real execution (exact 53/53 match — query scoped to `WindowedBootstrap`'s own `15:42:28→06:12:21` window **and** `@logStream like /warehouse-large/`) | **55,269 accessions attempted** (`attempted_accessions`), **10,837 idempotent skips** (`accessions_silver_skip`), **44,389 needed real network activity** (`accessions_with_network`), **114,172 total document-level network fetches** (`network_fetches` — multiple documents per accession) | 53 `filing_artifact_pipeline_completed` events, `stats sum(accession_count), sum(accessions_silver_skip), sum(accessions_with_network), sum(network_fetches)` |
| Records committed | **201,154 silver rows written** (`rows_written`) | same aggregation, `sum(rows_written)` |
| Rejects/errors | **43 summed `errors`** across the 53 completions; 2 verbatim samples from the same window: `WarehouseRuntimeError('SEC response exceeded size limit ... 135447380 bytes')` (accession `0001604028-25-000017`) and `TransientFilingContentError("... document_type ... SEC likely returned unexpected content ...")` (accession `0001225208-24-010223`) | CloudWatch Logs Insights, `filter event like /filing_artifact_failed/`, raw `@message`; sum from the aggregation above |
| Retries, duplicates | **0 `retry_count`, 0 `conflict_skipped_count`** summed across all 53 completions | same aggregation |
| Circuit breaker | `circuit_breaker_disposition: "closed"` on every sampled completion — never tripped | raw `@message` sample |
| Duration per window's sub-batch | 14–24 seconds observed (2 samples: 23.86s for 32 accessions, 13.96s for 28 accessions — samples from an adjacent, less-tightly-scoped query; order-of-magnitude consistent with the 53-window/14h30m total) | raw `@message` samples |

**Item vs. record distinction, explicit:** the CIK-window loop item count
(53) is a completely different axis from this section's 55,269 accessions
attempted / 201,154 rows committed — one CIK window can contain hundreds
of accessions, and this section's numbers are strictly downstream of, not
interchangeable with, §1's.

---

## 3. Stage 1B fundamentals maps (`load_history` — entity-facts / per-filing / thirteenf, each its own Distributed Map)

Same `cik_windows.jsonl` item source and 500-CIK window size as §1 (all
three re-read the identical manifest — `deploy-aws-application.sh:2503-2509`,
`:2567-2573`, `:2596-2602`), run **sequentially after** Branch A
(`WindowedBootstrap`) because all Branch B modes write the same silver
DuckDB file Branch A does.

| Map | MaxConcurrency | Item count (this execution) | Real outcome | Source |
|---|---|---|---|---|
| `Stage1BEntityFacts` (`bootstrap-fundamentals --mode entity-facts`) | 1 | 53 | **FAILED at item 1**: `succeeded=0, failed=1, aborted=1, pending=51` | `describe-map-run`, map-run 3 above (`656cc278-...`) |
| `Stage1BPerFiling` (`--mode per-filing`) | 1 | 53 | **FAILED at item 1**, identical shape | `describe-map-run`, map-run 4 (`853424f5-...`) |
| `Stage1BThirteenF` (`--mode thirteenf`) | 1 | 53 | **FAILED at item 1**, identical shape | `describe-map-run`, map-run 5 (`ae82e7e2-...`) |

All three attributions are now exact, resolved directly against
`get-execution-history`'s `MapStateEntered` state-name/timestamp pairs (see
the table at the top of §1) — no longer an inferred/unconfirmed mapping.

**AD-13 (documented design, confirmed live):** each Stage 1B stage's `Catch`
(`States.ALL` → next stage, `deploy-aws-application.sh:2488-2492,
2547-2551, 2552-2556`) means a **Map-level FAILED status does not abort the
execution** — the pipeline fell through EntityFacts→PerFiling→ThirteenF→
onward, all three showing the identical "item 1 fails/aborts, 51 never
start" pattern (consistent with a single root-cause bug hit immediately on
window 1's CIK-offset-0 batch, not exhausted retries across all windows —
`MaxConcurrency=1` + `ToleratedFailurePercentage=0` behaving as expected for
a strict sequential Map that stops fanning out further items once item 1
fails).

**Records processed:** not independently re-derived per Stage-1B-stage this
pass (would require the same tight per-map-run CloudWatch aggregation as
§1/§2, doable with the timestamps now in hand but not done for all three
stages given the effort budget); ~171 `entity_fact`-matching log lines were
observed per warehouse-medium log stream inside `Stage1BEntityFacts`'s own
06:12-10:38 window (`@message like /entity.fact/`, several distinct log
streams sampled), consistent with real per-window fundamentals activity on
at least window 1 before the stage failed, but not aggregated to a
verified total.

**A cross-cutting finding surfaced here, directly relevant to "records
committed":** despite this execution's **overall terminal status being
`FAILED`** (`aws stepfunctions describe-execution` → `status: FAILED`,
`stopDate: 2026-08-11T19:19:22-04:00`), a `gold_refresh` row for this
*exact* `run_id` (`ticket42-task35-fulluniverse-retry5-1786380966`) exists
in `EDGARTOOLS_PROD.EDGARTOOLS_SOURCE.SNOWFLAKE_REFRESH_STATUS` with
`STATUS: succeeded`, `SOURCE_ROW_COUNT: 20,966,689`, `TABLES_LOADED: 23`,
`MANIFEST_COMPLETED_AT: 2026-08-11 22:56:07 UTC` — and `GoldRefresh` does
appear later in this same execution's history (`TaskStateEntered` at
`2026-08-11T18:55:29-04:00`, after `MdmVerify` at `18:16:35`), consistent
with the pipeline reaching and completing gold publication despite the
Stage 1B failures upstream (per AD-13's fall-through design). **A
FAILED-terminal execution still produced and durably committed ~21M gold
rows to Snowflake.** This is the same class of masking this workstream's
Gate 5 already documented for `MdmVerify`'s `Catch`, but this is a fresh,
independently-found instance on the gold-commit side, not a repeat of that
finding — an operator reading only `list-executions`' `status` column for
this run would wrongly conclude zero records were committed.

---

## 4. CIK batches (`bootstrap-batch`, via `bronze_seed_silver_gold`'s `StrictBatchSilver` Distributed Map — `silver_mdm_gold`'s own `BatchSilver` Map has **zero executions ever**, see below)

| Dimension | Value | Source |
|---|---|---|
| Loop item | One explicit CIK list (not an offset/limit pair — batches carry the literal CIK values) | `deploy-aws-application.sh:3723-3730` (`cik_batches.jsonl` `ItemReader`) |
| Item source | `seed-bronze-batches` (`silver_mdm_gold`) or the shard-aware variant (`bronze_seed_silver_gold`'s strict branch) — lists CIKs straight from live S3 bronze, no SEC calls | `deploy-aws-application.sh:3701-3706, 3849-3852` |
| Batch size | 100 CIKs/batch (confirmed from real manifest, not just default) | `cik_batches.jsonl` for `bronze-seed-silver-gold-medium-20-retry-1786214600`, first line: 100 comma-separated CIKs |
| Item count, real execution | **680 batches**, nominally 100 CIKs/batch (680×100 = 68,000); the observed sum of `cik_count` across all 680 `bronze_capture_completed` events is **67,807** (193 fewer than the nominal 68,000 — some batches were under-full; the exact mechanism was not checked this pass) | `describe-map-run`, `itemCounts.total=680`; cross-checked via `cik_batches.jsonl` line count (`wc -l` = 680); CIK sum from the aggregation below |
| Map concurrency | `MaxConcurrency: 20` (raised from 4 same-day, 2026-08-08, after empirically ruling out `PromotionConflictError` contention at 20 — see source comment) | `deploy-aws-application.sh:4008-4009` (extensive inline history), confirmed live: `describe-map-run` `maxConcurrency: 20` |
| Real Map-run outcome | **680/680 succeeded, 0 failed** | `aws stepfunctions describe-map-run --map-run-arn arn:...bronze-seed-silver-gold/b978a440-...:e023b930-...`, execution `bronze-seed-silver-gold-medium-20-retry-1786214600`, captured 2026-08-12 |
| Duration | 2026-08-08T14:41:53 → 15:33:59 (-04:00) = **52m6s** for 680 batches at concurrency 20 | same `describe-map-run` |
| Records attempted | **67,807 CIKs**, **71,778 raw bronze objects touched**, **0 network fetches** (confirms the `--artifact-policy skip` invariant live, not just from source) | CloudWatch Logs Insights, `/aws/ecs/edgartools-prod-warehouse`, window 2026-08-08T14:30→15:40 (`1786213800`–`1786218000`); `stats sum(cik_count), sum(raw_object_count), sum(catalog_network_fetches)` over 680 `bronze_capture_completed` events (exact 680/680 match to the Map's own item count — no traceability gap here since the aggregation window is tight enough to be a clean 1:1 match) |
| Idempotent skips | **71,778** (`catalog_silver_skips` = `raw_object_count` exactly — every object was a cache hit) | same aggregation |
| Records committed (silver) | **1,259,036 rows written**, **50,801 rows skipped** (already-current) — from 680 `silver_apply_completed` events | same window, `stats sum(rows_written), sum(rows_skipped)` over `event=silver_apply_completed` |
| filing_artifact_pipeline events | **0** — confirmed the `--artifact-policy skip` / `--parser-policy skip` invariant directly (no SEC-fetch-shaped events at all in this run's full event-type breakdown) | same window, `stats count() by event` (full 19-event-type breakdown captured; no `filing_artifact_*` event present) |

**`silver_mdm_gold`'s own `BatchSilver` Map has never run in production**:
`aws stepfunctions list-executions --state-machine-arn
arn:...stateMachine:edgartools-prod-silver-mdm-gold` returns `[]` — zero
executions of any status, ever. This reproduces (and independently
re-confirms, live, 2026-08-12) the earlier Gate 4 audit's finding for this
same workflow. The 680/680 real production data above comes from
`bronze_seed_silver_gold`'s structurally-identical `StrictBatchSilver` Map
(same `cik_batches.jsonl`/`bootstrap-batch --artifact-policy skip` shape,
different state machine, different S3 manifest path) — a reasonable proxy
for the CIK-batch loop's real behavior, but not literally `silver_mdm_gold`
itself, which remains a config-only, never-executed loop.

**Item vs. record distinction, explicit:** 680 is the Map's item count.
67,807 CIKs / 71,778 raw objects / 1,259,036 silver rows are the records
those 680 items touched — an 1,850x multiplier between item count and rows
committed.

---

## 5. Stage0CompanyIdentityBounded (`daily_incremental` only — 500-CIK batches)

**Distinct from `load_history`'s (now-removed) `Stage0CompanyIdentity`**,
covered in §1's opening note: `daily_incremental` has its own, separate
`Stage0CompanyIdentityBounded` state (different name, different item
source — `cik_batches.jsonl` from `compute-identity-refresh-window`, not
`cik_windows.jsonl` from `compute-windows`), explicitly untouched by the
PR #396 removal per that commit's own message
(`write_warehouse_mdm_gold_definition`'s branch is a distinct code path
from `write_load_history_definition`'s).

| Dimension | Value | Source |
|---|---|---|
| Loop item | One explicit CIK list batch | `deploy-aws-application.sh:3417-3446` |
| Item source | `compute-identity-refresh-window` (`--mode daily` or `--mode backstop`), writing `cik_batches.jsonl` under the daily execution's own run prefix | `deploy-aws-application.sh:3377-3393` |
| Batch size | **500 CIKs/batch** (`--batch-size 500`, both `daily` and `backstop` modes) | `deploy-aws-application.sh:3390` (backstop mode's literal `'--batch-size', '500'`) |
| Item count, real (most recent execution with a manifest) | **3 batches** (up to 500 CIKs each) | `cik_batches.jsonl` for `daily-incremental-ticket89-unblocked-1785856213` (2026-08-04), `wc -l` = 3, first line = 500 comma-separated CIKs |
| Map concurrency | `MaxConcurrency: 1` | `deploy-aws-application.sh:3420` |
| Task profile | `wh_medium_arn` per-batch (`edgartools-prod-medium`, 1024 CPU/4096 MB); reducer step (`ReduceIdentityRefresh`) on `wh_large_arn` after a documented OOM on medium (`deploy-aws-application.sh:3401-3409`) | source |
| **Live record-level evidence** | **None available** — this execution (2026-08-04) is 8 days before this pass's 2026-08-12 capture date, outside the 7-day CloudWatch retention window. `list-executions` on `daily-incremental` shows **no execution at all since 2026-08-04** (most recent entry in a 10-row `list-executions` call is `daily-incremental-ticket89-unblocked-1785856213`) — i.e. `daily_incremental`, documented as the "ongoing" daily cadence workflow, has had **zero runs in the trailing 8 days** as of this capture | `aws stepfunctions list-executions --state-machine-arn arn:...daily-incremental --max-results 10`, captured 2026-08-12 |

**Item vs. record distinction:** 3 is the item count for this particular
day's window; the per-batch CIK/row counts that would complete the funnel
(selected/attempted/committed) are not recoverable for this execution —
flagged as an instrumentation-retention gap, not a "the pipeline does
nothing" claim.

---

## 6. Relationship types (`mdm backfill-relationships` / `mdm derive-relationships` — internal Python for-loop, not a Step Functions Map)

| Dimension | Value | Source |
|---|---|---|
| Loop item | One relationship type name | `edgar_warehouse/mdm/pipeline.py:697` (`for idx, rel_type_name in enumerate(requested_types)`) |
| Item source | `RELATIONSHIP_TYPES` constant — a fixed tuple of **11** types, or a CLI-supplied subset via `--relationship-type` | `edgar_warehouse/mdm/pipeline.py:80-94` |
| The 11 types, verbatim | `IS_INSIDER, HOLDS, COMPANY_HOLDS, ISSUED_BY, IS_ENTITY_OF, HAS_PARENT_COMPANY, MANAGES_FUND, IS_PERSON_OF, EMPLOYED_BY, AUDITED_BY, INSTITUTIONAL_HOLDS` | same |
| "Batch size" within one type | No batching for most types; `INSTITUTIONAL_HOLDS` specifically reads `sec_thirteenf_holding` in **1,000-CIK range chunks** (`_INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE = 1000`) because it is the largest silver table | `edgar_warehouse/mdm/pipeline.py:96-102` |
| Real execution, standalone `mdm-backfill-relationships` SM | `aws-mdm-e2e-1786310173-backfill`, 2026-08-09, `SUCCEEDED`, ECS command `mdm backfill-relationships --limit 100`, ran on `edgartools-prod-mdm-medium:143` | `aws stepfunctions describe-execution` |
| Item count | **11/11 types visited** (`types_done` counts 1→11 across the run) | 11 `mdm_progress` (`domain=relationships`) events, CloudWatch Logs Insights, window 2026-08-09T17:19:00–17:29:00 |
| Per-type records, real (all 11, exact) | `IS_INSIDER`: existing 1,193, inserted 0. `HOLDS`: existing 2,050, inserted 0. `COMPANY_HOLDS`: existing 17,058, inserted 0. `ISSUED_BY`: existing 2,906, inserted 0. `IS_ENTITY_OF`/`HAS_PARENT_COMPANY`/`IS_PERSON_OF`/`EMPLOYED_BY`/`AUDITED_BY`/`INSTITUTIONAL_HOLDS`: existing 0, inserted 0. `MANAGES_FUND`: existing **563,631**, inserted 0. All types: `skipped=0` (no rejects/dupes surfaced this run), `target=5` (per-type target — see caveat) | verbatim `@message` fields from the same 11 events |
| Duration | 2026-08-09T21:19:13.859 → 21:19:16.862 UTC ≈ **3.0 seconds total** for all 11 types (every type already at/above its target — a pure no-op verification pass, not a real backfill) | same events' `@timestamp` |
| Caveat on `target=5` | The ECS override was `--limit 100`, but the emitted `target` field on every type was `5`, not 100 — `--limit` and `derive_relationships`'s `target_per_type` parameter are evidently not the same value in this invocation; not resolved further this pass (would require reading `cli.py`'s exact `--limit`→`target_per_type` wiring), flagged as an open question rather than guessed at | `aws-mdm-e2e-1786310173-backfill`'s ECS override (`"Command":["mdm","backfill-relationships","--limit","100"]`) vs. every `mdm_progress` event's `"target": 5` |
| A real, non-zero-insert relationship backfill | Not found within the 7-day retention window — the last real bulk `INSTITUTIONAL_HOLDS`/`EMPLOYED_BY` inserts on record (`edge11-institutional-holds-fullrun-1785098441`, `edge09-employed-by-postfix3-1785108623`, both 2026-07-26) are **17 days outside** current retention; their logs are gone. Flagged as an instrumentation-retention gap, not "these types never insert" — CLAUDE.md's own "INSTITUTIONAL_HOLDS / EMPLOYED_BY" and "Bronze-recovery" 5-whys sections document real historical inserts for exactly these types | `list-executions` timestamps vs. `retentionInDays: 7` |
| Standalone-CLI relationship-type scoping (contrast) | `residual_holds_graph` and `ownership_mdm_gold` do **not** use the 11-type internal loop at all — each calls `mdm derive-relationships --relationship-type <ONE>` as its own separate, named ECS Task state (`MdmIsInsider`, `MdmHolds`, `MdmCompanyHolds`, `MdmInstitutionalHolds`, each a distinct state, not a loop) | `deploy-aws-application.sh:4665-4779` |

**Item vs. record distinction, explicit:** 11 is the type-loop's item
count. 1,193 / 2,050 / 17,058 / 563,631 (etc.) are the row-level record
counts *per item* — MANAGES_FUND alone (563,631) outweighs every other
type combined by >20x, illustrating why a flat "11 items" figure says
nothing about relative record cost.

---

## 7. Generation partitions (`generation_build` — `BuildPartitions` Distributed Map)

| Dimension | Value | Source |
|---|---|---|
| Loop item | One partition: a `(kind, type_name, shard_index)` triple — one per active MDM node type or relationship type (sharded further only if a type's row count requires it) | `deploy-aws-application.sh:4305-4331` |
| Item source | `mdm generation-plan` freezes a watermark and writes `partitions.jsonl` to `s3://.../reference/mdm_generation/runs/<execution-name>/partitions.jsonl` | `deploy-aws-application.sh:4312-4315, 4338-4345` |
| Batch size | 1 partition = 1 ECS task (no sub-batching) | source |
| Map concurrency default | **8** (`--mdm-generation-partition-concurrency`, default `MDM_GENERATION_PARTITION_CONCURRENCY=8`) | `deploy-aws-application.sh:207, 4336` |
| `ToleratedFailurePercentage` | **100** — a single partition failing is not fatal to the whole Map; `FanIn` (a separate state) is the sole pass/fail authority | `deploy-aws-application.sh:4325-4327, 4337` |
| Item count, only-ever execution | **17 partitions**: 6 node types (`adviser, audit_firm, company, fund, person, security`) + 11 relationship/edge types (the identical 11 from §6) — all `shard_index: 0`, i.e. no type needed further sharding at this data volume | `s3 cp .../ticket20-e2e-validate5-20260722T203009-generation-build/partitions.jsonl -`, 17 lines, verbatim content quoted |
| Execution status | `SUCCEEDED`, 2026-07-22T20:30:14 → 20:36:52 (-04:00), **6m38s** | `list-executions` |
| **This is the state machine's only execution ever** | `aws stepfunctions list-executions --state-machine-arn arn:...generation-build` returns exactly 1 row, no others | captured 2026-08-12 |
| Live record-level evidence | **None available** — 2026-07-22 is 21 days before this pass, far outside 7-day retention. The generation this run produced (`056426c8-538d-4c32-9030-bcadced29e24`, from `generation.json`) **no longer exists** in `EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION.GRAPH_GENERATION` at all — that schema was wiped and recreated 2026-08-07/08-09 (per this repo's own "MDM Snowflake mirror schema lost on cutover" incident note); the current table's 4 rows (re-verified live below) all postdate this run | S3 manifest (durable) vs. Snowflake `GRAPH_GENERATION` (recreated, no history before 2026-08-09) |

**Re-verification of `GRAPH_GENERATION` (per the ticket's instruction to
re-verify Gate 4's row count/values, not re-derive from scratch):**

```sql
SELECT GENERATION_ID, STATUS, NODE_COUNT, EDGE_COUNT, CREATED_AT, ACTIVATED_AT
FROM EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION.GRAPH_GENERATION ORDER BY CREATED_AT;
```

| GENERATION_ID | STATUS | NODE_COUNT | EDGE_COUNT | CREATED_AT (PDT) | ACTIVATED_AT |
|---|---|---|---|---|---|
| `ea5f6626-...` | failed | 223,466 | 586,768 | 2026-08-09 06:51:03 | — |
| `b199942c-...` | activated | 223,466 | 586,768 | 2026-08-09 07:05:07 | 2026-08-09 07:08:22 |
| `5cbdc701-...` | building (stuck) | **100** | **100** | 2026-08-09 14:29:10 | — |
| `7fc87ef9-...` | building (stuck) | **200** | **200** | 2026-08-11 15:15:45 | — |

Still exactly 4 rows, identical values to Gate 4's 2026-08-11 capture —
**confirmed unchanged**, 2026-08-12, `snow sql --connection edgartools-prod`.

## 7a. Graph-sync batches (`mdm sync-graph`)

Not a Step Functions Map — a single ECS command whose internal batching is
controlled by `--limit` (default `MDM_GRAPH_LIMIT=200` for
`daily_incremental`'s embedded `mdm_sync` state, `deploy-aws-application.sh:203,
1276-1284`). The two "stuck at 100/200" `GRAPH_GENERATION` rows above are
direct, exact evidence of this limit in action — not sync failures.

| Dimension | Value | Source |
|---|---|---|
| Real execution | `aws-mdm-e2e-1786310173-sync`, 2026-08-09, `SUCCEEDED`, ECS command included `--limit 100` (this run used the E2E driver's own explicit 100, not `daily_incremental`'s 200 default) | CloudWatch `@message`: `"arguments": {..., "limit": 100, ...}, "command": "sync-graph", "event": "mdm_command_started"` |
| Records synced | `graph_nodes_synced: 100`, `graph_edges_synced: 100`, `graph_nodes_materialized: 100`, `graph_edges_materialized: 100` — an exact 1:1 hit of the `--limit` ceiling | same window, raw `@message` (multi-line pretty-printed JSON in the log stream) |
| Duration | `duration_ms: 22447` (22.4s) | `mdm_command_completed` event, same window |
| Corresponding `GRAPH_GENERATION` row | `5cbdc701-8d66-4331-a8a9-3f743682d8af`, `CREATED_AT: 2026-08-09 14:29:10 -07:00` = `2026-08-09T21:29:10Z`. Against this section's own `mdm_command_started`/`mdm_command_completed` timestamps (`21:29:06.5Z` start, `21:29:28.9Z` complete, `duration_ms: 22447`), the generation row's `CREATED_AT` (`21:29:10Z`) falls **inside** this command's own run, ~4s after it started and ~19s before it finished — consistent with `sync-graph` creating the `GRAPH_GENERATION` row early in its own execution, before the materialization work that produces the final 100/100 counts completes. (Gate 4's own write-up anchored a "44 seconds after" figure against the *Step Functions* `SUCCEEDED` timestamp — `21:29:56Z` per `list-executions` — not this section's `mdm_command_completed` line; the two anchors are different events and should not be combined into one figure.) | cross-referenced timestamps, both independently pulled this pass |

**Item vs. record distinction:** "sync-graph" itself is not iterated by a
Map — the "batch" here is the single `--limit` value bounding one command's
internal materialization pass; 200 (`daily_incremental`'s default) or 100
(this E2E-driver run) is a **record cap**, not a loop-item count.

---

## 8. MDM limits (`MDM_RUN_LIMIT`, `MDM_GRAPH_LIMIT` — `daily_incremental`'s bounded MDM tail)

| Env var | Default | Used by | Source |
|---|---|---|---|
| `MDM_RUN_LIMIT` | **100** | `daily_incremental`'s `mdm run --entity-type all --limit 100` | `deploy-aws-application.sh:202, 1269-1270` |
| `MDM_GRAPH_LIMIT` | **200** | `daily_incremental`'s `mdm backfill-relationships --limit 200` and `mdm sync-graph --limit 200` | `deploy-aws-application.sh:203, 1276-1284` |
| `MDM_GENERATION_PARTITION_CONCURRENCY` | 8 | `generation_build`'s `BuildPartitions` Map (§7) | `deploy-aws-application.sh:207, 4336` |
| `BOOTSTRAP_BATCH_CONCURRENCY` | 3 (but overridden to 20 in the real §4 run) | `silver_mdm_gold`'s `BatchSilver` Map (never executed) | `deploy-aws-application.sh:195` |

**Explicit invariant, confirmed in source:** `silver_mdm_gold`/
`bronze_seed_silver_gold`'s full-bulk MDM tail deliberately does **not**
pass `--limit` at all (`mdm_run = ecs_state(..., "States.Array('mdm', 'run',
'--entity-type', 'all')", ...)`, `deploy-aws-application.sh:3744` — no
`--limit` argument) — `MDM_RUN_LIMIT`'s 100 default is intentionally
**not** used there, only for `daily_incremental`'s bounded incremental tail
(inline comment: *"a hard limit would silently leave the majority of
companies unprocessed"*).

**Live evidence:** the standalone E2E-driver `mdm run` execution
(§6, `aws-mdm-e2e-1786310173-run`) used `--limit 5` (a deliberately tiny
smoke-test value, not either production default) — `"arguments": {...,
"limit": 5, ...}`. No `daily_incremental` execution exists within the
7-day retention window to observe the **production** `--limit 100`/`--limit
200` values firing live (§5's finding: zero `daily_incremental` executions
in the trailing 8 days) — this is a real, current gap, not filled by the
E2E driver's unrelated smoke-test value.

---

## 9. Other loops noted but out of primary scope / not independently measured this pass

- **`compute-identity-refresh-window --mode backstop`** (`daily_incremental`,
  same 500-CIK batch shape as §5's `--mode daily`) — not separately
  measured; same live-evidence gap as §5 applies.
- **MDM entity-resolution row loops** (`run_companies`, `run_securities`,
  `run_persons` in `pipeline.py`) — each logs `mdm_progress` at an interval
  of `max(1000, total_rows // 8)` (`edgar_warehouse/mdm/pipeline.py:62-78`);
  no instance of these specific progress lines was captured in the
  CloudWatch windows sampled this pass (the two `mdm run` executions
  sampled, §6 and §8, used `--limit 5` and were too small/fast to cross the
  1,000-row logging floor). Confirmed to exist in source; not confirmed
  live.
- **ADV bulk fetch** (`AdvBulkFetch` stage, `deploy-aws-application.sh:2616+`)
  — mentioned in `load_history`'s Stage 1 comments as a monthly
  archive-ingest step; not traced for Map/loop shape this pass.
- **`daily-index` catch-up loops** (`catch-up-daily-form-index`,
  `load-daily-form-index-for-date`) — both **zero executions ever**
  (re-confirmed live via `list-executions`, matching Gate 3's "Chain I"
  finding), so there is no loop to measure.

---

## Instrumentation-gap summary (for tickets 13/15/16/17, which depend on this inventory)

1. **Distributed Map child `run_id` UUIDs are uncorrelated to the parent
   execution name** (top of this document) — the single biggest gap. No
   CloudWatch query can cleanly attribute per-window/per-batch log lines to
   one specific parent execution without a wall-clock-window heuristic,
   which is inherently approximate when multiple executions overlap in time
   (as several did across 2026-08-08 through 2026-08-11 in this account).
2. **7-day CloudWatch retention** means any workflow whose most recent
   execution is >7 days old (which, as of 2026-08-12, includes
   `daily_incremental`'s only recent run at 8 days, `mdm-backfill-relationships`'s
   only real-insert runs at 17 days, and `generation_build`'s only-ever run
   at 21 days) has **zero** log-line-level record-funnel evidence available
   — only S3-manifest-level item counts (durable) and source-code defaults
   survive.
3. **`ECS/ContainerInsights` CPU/Memory metrics are dimensioned by
   `(ClusterName, TaskDefinitionFamily)` only** — no per-task or
   per-execution dimension exists in what's currently enabled. A "peak
   memory for this one execution's large-family tasks" figure is only
   approximable by narrowing the metric query's time window to match the
   execution's own start/stop, and even then may include other
   concurrently-running executions' tasks in the same family. True
   per-task peak (e.g., "did window 37 specifically approach the 8192 MB
   ceiling") is not recoverable after the task stops; `aws ecs
   describe-tasks` only returns live/recently-stopped tasks, not a queryable
   history.
4. **`daily_incremental` has had zero executions in the trailing 8 days**
   as of this capture — the workflow CLAUDE.md and this workstream's own
   docs describe as "ongoing"/ the production cadence has no recent
   evidence of actually running, at all, in either logs or Step Functions
   execution history.
5. **`silver_mdm_gold` has zero executions ever** (re-confirmed live) — its
   `BatchSilver` Map's config (§4) is real and deployed but has never fired;
   all real evidence for that Map *shape* comes from a structurally
   identical but distinct state machine (`bronze_seed_silver_gold`'s
   `StrictBatchSilver`).
6. **A masked-success instance found while building this inventory** (§3):
   a `load_history` execution with overall `FAILED` terminal status still
   durably committed ~21M gold rows to Snowflake under its own `run_id`.
   Any tooling that infers "records committed = 0" from a `FAILED` Step
   Functions status alone will be wrong for this exact execution, and
   plausibly others — not re-derived exhaustively here (out of this
   ticket's scope), but load-bearing for tickets that build unit-economics
   or telemetry contracts (13, 17) on top of Step Functions terminal status.
7. **CLAUDE.md's "Phased Pipeline" Stage 0 description is stale for
   `load_history`** (§1's opening note) — `Stage0CompanyIdentity` was
   removed from `load_history` by PR #396 (commit `da8ccb65`,
   2026-08-10T18:35:39-04:00) and now only exists in `daily_incremental`'s
   separate `Stage0CompanyIdentityBounded` branch (§5). This document's
   own primary-evidence execution (§1-3) ran its `Stage0CompanyIdentity`
   pass 3.5 hours *before* that commit merged — real production evidence
   of a stage that no longer exists in current source. Anyone using
   CLAUDE.md's current Phased Pipeline section to reason about
   `load_history`'s *current* loop structure will mis-model it.
8. **The `mdm backfill-relationships --limit 100` vs. `target: 5` mismatch**
   (§6) was observed but not root-caused this pass — flagged as an open
   question about what `--limit` actually threads into on that code path.
