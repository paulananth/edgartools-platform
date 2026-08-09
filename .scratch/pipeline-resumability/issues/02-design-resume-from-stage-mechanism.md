Type: grilling
Status: resolved

## Question

Design the resume-from-stage mechanism that ticket 01 concluded is still
needed for `bronze_seed_silver_gold` (and potentially other long pipelines)
to actually skip already-completed work on a restart, instead of either
(a) fully redoing a stage from scratch (BatchSilver today) or (b) being
merely idempotent-safe-to-redo without being faster (MdmRun's company step
after PR #376).

Grounding: `edgar_warehouse/application/daily_artifact_resume.py` already
implements this exact shape of problem for `daily_incremental` — an
immutable, digest-verified run manifest plus per-item immutable S3 outcome
markers (`succeeded` / `terminal_repair_required`), with a batched
existence check (`_list_outcome_statuses`) computing pending work as
"selected minus already-succeeded." CONTEXT.md documents this as the
**Daily-Artifact Run Manifest** / **Daily-Artifact Outcome Ledger** pattern.
This ticket decides whether/how to extend that same pattern to
`BatchSilver` (CIK batches) and `MdmRun` (per-CIK company resolution,
and eventually security/person), or whether a different mechanism fits
those stages' shape better.

Resolve via `/grilling` + `/domain-modeling` per this map's Notes.

## Answer

**Scope**: `BatchSilver` and `MdmRun`'s company step only. `run_securities`/
`run_persons` are excluded — they're still single-commit-at-end (not yet
safely interruptible, per [mdm-run-throughput](../mdm-run-throughput/map.md))
and giving them a resume marker before that foundation lands would be
building on unstable ground.

**Trigger**: an explicit `resume_from_run_id` field on the state machine's
`start-execution` input. Not auto-detected — matches this repo's existing
preference for explicit gates (`release_mode`, `--force`) over implicit
auto-detection, since silently resuming onto the wrong prior run's ledger
would be a hard-to-detect correctness bug, not a loud one.

**Effective run id**: every S3 path either stage touches is scoped by
`resume_from_run_id` when present, else `$$.Execution.Name` — so the whole
pipeline stays logically "one run" across any number of stop/restart
cycles, and a resume-of-a-resume keeps accumulating against the same
ledger namespace rather than chaining through multiple prior run ids.

**Frozen candidate lists, never regenerated on resume**: `SeedFromBronze`
is skipped entirely when `resume_from_run_id` is set. Implementation
refinement over the original phrasing here: `BatchSilver`'s `ItemReader`
always reads from `runs/{$$.Execution.Name}/cik_batches.jsonl` (avoids a
Choice-based branch on the ItemReader's own Key) — but on resume, the new
`ComputeRemainingBatches` state populates that file by filtering the
*original* run's frozen `cik_batches.jsonl` (read from
`resume_from_run_id`'s path) down to not-yet-done batches, never by
re-deriving candidates from bronze. The invariant holds (candidate set is
never re-derived from live data on resume), just via a filtered copy
instead of a literal shared file. Same for MdmRun's company candidates:
the CIK list is snapshotted once to S3 at first-attempt start and reused
verbatim on resume, not re-queried from `sec_company` live. This mirrors
`daily_artifact_resume.py`'s own rule (CONTEXT.md: *"it is the only
candidate set a resume may use"*) — reusing the frozen list guarantees
batch/marker identity stays stable even if bronze or `sec_company` drifted
between attempts. Accepted tradeoff: a resumed run will not pick up
brand-new CIKs discovered after the original run started; those get
picked up by the next regular `daily_incremental` or full
`bronze_seed_silver_gold` run, same as today.

**BatchSilver mechanism — reuse existing code, don't reinvent**:
`edgar_warehouse/application/relationship_bulk_load.py` already implements
this exact job for the `StrictBatchSilver`/`release_mode` path — Ticket 20
P0's `batch_identity_for_ciks()` (a content-derived hash of each batch's
sorted CIK list, not run-id-keyed), `batch_done_marker_path()`, and
`build_remaining_cik_batches()` (drops any batch whose identity already has
a done marker). The only gap is that today it's wired up only through a
**manual** operator script
(`edgar_warehouse/scripts/build_remaining_release_batches.py`) for the
strict path, which also has to re-derive `freeze_prefix`/
`candidate_manifest_key` — ceremony specific to strict release mode that
the default path doesn't need. For default `BatchSilver`, add a new
`ComputeRemainingBatches` Task state before the Map (inserted only on the
`resume_from_run_id` branch), calling the same `list_done_batch_identities`/
`build_remaining_cik_batches` functions directly as a library call — same
proven logic, automatic instead of a manual per-incident script run.
Done markers get written under the effective run id's own prefix
(mirroring where `cik_batches.jsonl` already lives:
`warehouse/bronze/reference/cik_universe/runs/{effective_run_id}/batch_done/{identity}.json`),
written by `bootstrap-batch` itself after each batch's real success —
independent of the strict path's `freeze_prefix`, which stays untouched.

**MdmRun mechanism — same conceptual shape, batched instead of per-item**:
`run_companies` already commits per-row (PR #376), so it's safe to
interrupt; it just isn't skip-ahead on restart. Add: (1) a one-time CIK
snapshot written to S3 at first-attempt start (or reused on resume); (2)
batched outcome flushes — accumulated succeeded-CIKs written as one JSON
array object every `log_interval`-scale threshold (reusing the cadence
shape from `_progress_log_interval`, PR #377) instead of one S3 object per
company. At MdmRun's 62,190-row scale, per-item markers (matching
`daily_artifact_resume.py`/BatchSilver exactly) would mean ~62K S3 PUTs
per full run — not expensive, but a real departure from what those
patterns were sized for; batching keeps request volume proportional to
log-interval granularity (dozens of objects, not tens of thousands) at the
cost of losing at most one interval's worth of already-succeeded-but-
unflushed work on a stop mid-interval — a fine tradeoff since re-resolving
a handful of already-done companies is idempotent and cheap. Unlike
BatchSilver, no separate ASL prep state is needed: MdmRun is a single ECS
Task, not a Map, so there's no "avoid launching wasted Fargate tasks"
concern that forces filtering to happen before the task starts. The
remaining-computation is self-contained in Python: `mdm run
--resume-from-run-id <id>` reads its own prior CIK snapshot plus flushed
outcome-batch files at the top of `run_companies`, computes the remaining
CIK set internally, and proceeds — no new state-machine step.

**Fail-closed on a bad resume pointer**: if `resume_from_run_id` is present
but no manifest/snapshot exists under its prefix (typo, wrong id, prefix
never written), error out clearly — a new `ResumeRunNotFound`-style Fail
state (BatchSilver) / raised `WarehouseRuntimeError` (MdmRun's Python path)
— rather than silently falling back to a fresh run. Matches the existing
`StrictInputMissing` fail-closed precedent for `release_mode`'s own
required-field validation.

**Status**: design locked, matching this map's Destination ("a written,
evidence-backed decision... that someone can implement without further
architecture debate"). Per this map's planning-first default (no "this map
carries execution" override in Notes), **implementation has not started**
— this ticket documents the decision only. A follow-up implementation
pass would touch: `deploy-aws-application.sh` (new `resume_from_run_id`
Choice branching, `ComputeRemainingBatches` state, `SeedFromBronze` skip),
`edgar_warehouse/mdm/pipeline.py` (`--resume-from-run-id` CLI plumbing,
snapshot + batched-flush logic in `run_companies`), and new tests
mirroring `daily_artifact_resume.py`'s and
`test_run_companies_concurrency.py`'s existing coverage shape.
