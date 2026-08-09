# Pipeline resumability

Labels: wayfinder:map

## Destination

A locked decision on how the platform's long-running Step Functions
pipelines (`bronze_seed_silver_gold`, `load_history`, `daily_incremental`,
`bootstrap_full`, `full_reconcile`, and the `mdm_*` chain) should recover
from an operator-initiated stop or a real failure — resuming from the last
completed point instead of a full `start-execution` from Stage 0 — where
that's safe and worthwhile given the work each stage has already made
idempotent. Done when there's a written, evidence-backed decision on the
mechanism (AWS Step Functions' native `RedriveExecution`, a custom
checkpoint/resume input pattern, or "not worth it because the cheap stages
already tolerate a restart") that someone can implement without further
architecture debate.

## Notes

- Domain: `infra/scripts/deploy-aws-application.sh` (state machine
  definitions), `edgar_warehouse/application/warehouse_orchestrator.py`.
- Trigger: 2026-08-08 live `bronze_seed_silver_gold` execution
  (`bronze-seed-silver-gold-1785...`, aborted mid-`MdmRun` to ship the
  `run_companies` concurrency fix, PR #376) had to be restarted from Stage
  0 via `start-execution` — BatchSilver's 680 batches re-ran (cheaply,
  thanks to the bronze SHA256 cache — see
  [pipeline-throughput-architecture](../pipeline-throughput-architecture/map.md)
  ticket 11's evidence, ~77s/batch even on a cache-hydrate path) but
  MdmRun's ~1000/62,190-company progress was lost outright, because at the
  time `run_companies` held one session open for the whole domain and
  committed once at the end. PR #376 already fixes that specific loss
  going forward (per-row commit) — this map is about the *orchestration*
  layer having no resume primitive at all, independent of that fix.
- Standing preference from the parent session: real measurements over
  estimates; verify AWS feature claims (retention windows, Distributed Map
  semantics, definition-change constraints) against primary docs, not
  memory.

## Decisions so far

1. [Research AWS Step Functions RedriveExecution fit](issues/01-research-step-functions-redrive-execution.md) — resolved: native redrive is a real but partial fit. It's STANDARD-only (this platform is all-STANDARD, confirmed), eligible for ABORTED executions (an operator `StopExecution` qualifies), 14-day window from stop/completion, and for `BatchSilver`'s Distributed Map it resumes only the failed/canceled child batches — not a full Map restart. But it's decisively ruled out for the pattern that actually triggered this map: AWS's own docs confirm a redrive replays the state machine definition frozen at the *original* execution's start time, never a definition deployed after the stop — so redriving after "stop to ship a fix" would silently resume the stale pre-fix ASL. `MdmRun` is a plain sequential Task (not a Map), so none of the per-child redrive granularity helps there either.
2. [Design resume-from-stage mechanism](issues/02-design-resume-from-stage-mechanism.md) — resolved: an explicit `resume_from_run_id` execution input, scoping every S3 path by that effective run id, with frozen (never-regenerated) candidate lists on resume. BatchSilver reuses `relationship_bulk_load.py`'s existing Ticket-20-P0 `batch_identity_for_ciks`/`build_remaining_cik_batches` machinery automatically (a new `ComputeRemainingBatches` state) instead of its current manual-script-only wiring. MdmRun gets a one-time CIK snapshot plus batched (not per-item) outcome flushes, filtered self-contained in Python via `--resume-from-run-id`, no new ASL state needed. Fails closed on an invalid resume pointer. Scoped to BatchSilver + MdmRun's company step only. Design locked; **implementation not started**.

## Not yet specified

- Whether native redrive is still worth wiring up as a *secondary*
  fast-path for pure infra-flake retries (no definition change involved)
  even though it can't cover the primary trigger — a smaller, separate
  question from ticket 02's design, not addressed there.
- Whether `run_securities`/`run_persons` or the ownership/ADV
  artifact-fetch stages need the same resumability treatment — deferred in
  ticket 02 until they're safely interruptible at all (see
  [mdm-run-throughput](../mdm-run-throughput/map.md)).

## Out of scope

- Re-litigating BatchSilver's own throughput or the bronze SHA256 cache
  design — already decided in
  [pipeline-throughput-architecture](../pipeline-throughput-architecture/map.md).
- Re-litigating `run_companies`' per-row commit fix — already shipped
  (PR #376); this map is about the state-machine layer having no resume
  primitive, not about individual stages' own idempotency.
