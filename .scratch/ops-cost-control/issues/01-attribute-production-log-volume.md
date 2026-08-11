# Attribute Production Log Volume by Event Family

Type: task
Status: resolved
Blocked by: none

## Question

Which production ECS and Step Functions event families, source call sites, and
workflows account for the ingested bytes and record counts during a bounded
representative execution?

Capture a secret-safe baseline using CloudWatch Logs Insights and code-to-event
mapping. Rank contributors by bytes and records, distinguish routine per-record
events from stage summaries and actionable failures, and bind the evidence to
the immutable image and execution. Do not change logging while measuring.

## Answer

Decided/measured 2026-08-11. No logging code changed, per the ticket's own
constraint — this is measurement only.

**Live state re-verified, not assumed from the map's baseline (which is now
stale on one point):** `aws logs describe-log-groups` shows current retention
on `/aws/ecs/edgartools-prod-warehouse` and `/aws/states/edgartools-prod-warehouse`
is **30 days**, not the seven days the map's Notes claim was applied
2026-08-01 — a live discrepancy, flagged here for
[ticket 03](03-make-seven-day-log-retention-durable.md) to resolve, not
fixed by this ticket. Current stored bytes have grown substantially past
the map's baseline snapshot, driven largely by this session's own
full-universe `load_history` backfill: ECS execution group 1,121,707,764
bytes (baseline: 732,476,026, +53%), Step Functions group 25,030,837
(baseline: 12,045,337, +108%), Container Insights performance group
9,514,083 (baseline: 557,657, +1,606%).

**Representative execution:** Stage 1 (`WindowedBootstrap`) of the
currently-running full-universe `load_history` execution
(`ticket42-task35-fulluniverse-retry5-1786380966`), 2026-08-10T15:42:28-04:00
to 2026-08-11T06:12:21-04:00 (~14 hours), bound to warehouse image digest
`sha256:45fe27c688ca4e9d9a0b5bf6761d4316332d188d4fcbb7cccddd2506aa4793b2`
(confirmed the currently-deployed digest at measurement time). Chosen over
a routine `daily_incremental` run because it is the dominant real
contributor to current log growth, not a hypothetical worst case.

**CloudWatch Logs Insights aggregation** (`stats sum(strlen(@message)),
count(*) by event_type`, parsed from the structured `"event": "..."` field
present on most log lines) over that window: 1,313,678 log records / 206 MB
scanned. Ranked findings:

1. **Largest contributor by both bytes (61.9M, ~37% of matched volume) and
   records (938,025, ~71% of all records): an unstructured bucket that
   turned out to be the single most important finding, not noise.**
   Sampled it directly — these are not free-form log lines at all, they are
   individual lines of a **pretty-printed (`indent=2`), multi-thousand-line
   JSON dump of the full command result payload**, printed once at the end
   of every command invocation. That payload includes the complete
   `raw_writes` manifest — one full receipt (S3 `path`, `relative_path`,
   `sha256`, `raw_object_id`, `cik`, `cached` flag) **per document written**
   during the entire command run. Pinned to source: two near-duplicate call
   sites do this identically —
   `edgar_warehouse/application/warehouse_orchestrator.py:265`
   (`run_command`) and
   `edgar_warehouse/application/workflows/command_runner.py:39`
   (`execute_standard_command`), both
   `print(json.dumps(payload, indent=2, sort_keys=True))`. This is
   diagnostic output intended for a human reading a local CLI invocation,
   captured wholesale as production log volume because ECS routes task
   stdout straight to CloudWatch.
2. **Second tier — genuinely structured, but extremely high-cardinality
   per-record events** (routine, not stage summaries or failures):
   `sec_pull_completed`/`sec_pull_started` (32.1M + 21.3M bytes, 69,454 +
   64,165 records), `artifact_content_fetch_started`/`_completed` (18.5M +
   14.5M bytes, 64,966 + 69,623 records), `sec_call_completed`/`_started`
   (7.2M + 6.2M bytes, 44,432 records each) — one event per SEC HTTP call
   or per document fetch, ~100M bytes combined across this one window.
3. **Stage summaries and completion events are already a small fraction of
   total volume** — e.g. `filing_artifact_pipeline_completed` (53 records,
   29,832 bytes for the entire 14-hour window),
   `bronze_silver_completed`/`silver_publish_completed`/
   `bronze_capture_completed` all similarly small (10-59K bytes, 53 records
   each — one per window, exactly as intended). These are not a
   contributor worth targeting.
4. **Actionable failures are negligible in volume**: `sec_pull_failed` (1
   record), `artifact_content_fetch_failed` (2 records),
   `filing_artifact_failed` (43 records) — failures are rare and cheap;
   they are not part of the cost problem.

**Net ranking, answering the ticket's question directly:** the dominant
contributor is neither a "stage summary" nor an "actionable failure" — it's
a **per-command diagnostic dump never intended for production capture**
(finding 1), followed by legitimate but very fine-grained per-record
operational events (finding 2) that are working as designed but are
high-volume by nature of processing hundreds of documents per window.
Stage summaries (finding 3) and failures (finding 4) are already
appropriately small and need no changes.

This directly informs, but does not itself decide, remediation shape —
that's [ticket 02](02-replace-routine-record-logs-with-summaries.md)'s
job. The clearest, lowest-risk win visible from this data: finding 1's
pretty-printed full-payload dump could plausibly be removed or
compacted (it duplicates data already durably captured in S3/the run
manifest — CLAUDE.md's own Daily-Artifact Run Manifest / Outcome Ledger
concept) without touching any of the legitimate per-record operational
events in finding 2, which the map's Notes correctly caution against
merging into stage summaries without more thought.
