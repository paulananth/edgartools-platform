# Retained load timing reports

Use this procedure for load-time and initialization-to-entity reports. Limit report generation to **five minutes**; this is not a production load benchmark.

## Prepare the runtime before timing

Before starting the report clock, use a project environment with MDM runtime dependencies. In a fresh worktree, initialize it once with `uv sync --extra s3 --extra mdm-runtime`. `uv run --no-sync` does not install dependencies; on an empty worktree it can create an environment where the profiler fails to import SQLAlchemy. If setup is not ready, report from retained evidence and mark live profiling unavailable. Do not spend the report deadline bootstrapping dependencies.

Invoke the skill's `scripts/profile_load.py` from its directory using the prepared project environment. Always pass the exact `--run` to `steps`. The profiler's `steps` view reads Bookkeeping; use it only when the environment and access gates permit that connection.

## Five-minute workflow

1. **Scope once (first minute).** Resolve the environment and private evidence directory. Read the configured source/target inventory and dependency list once; obtain the entity-kind map from active Dataset Contracts, not source names. Check credential and hosted-qualification gates before live access. An uncleared gate means retained-only evidence, not a reason to investigate provisioning or rotate credentials. Keep every requested target in the report.
2. **Reuse, then batch (next two minutes).** Read existing measurement JSON, explicit load summaries and manifest indexes before raw logs. Reuse artifacts with their observation times and code/Rules versions. Verify only missing or stale fields through supported read-only commands. Prefer an existing batch reader; otherwise bound status and profiler calls by the remaining deadline. Retain every bundle run ID, but do not query each bundle when a retained verified snapshot covers them. Search only resolved evidence directories; read large receipt bodies or failure logs only to resolve a specific field.
3. **Calculate once (fourth minute).** Group per-run evidence by source/target and kind, preserving exact step names. Verify complete state, expected units equal verified units and zero pending deliveries. A snapshot proves its observation time, not current state; label unverified logs historical. Reconcile `considered = selected + already_processed` per invocation without adding overlapping attempts. Compute first contribution from the **earliest verified run completion**, not the minimum of each target's final completion. All-source completion requires every active contributing contract and required link target; source records are not unique masters.
4. **Write and check (by minute five).** Produce one private report and reusable structured evidence snapshot with observation time, environment label, code/Rules versions, evidence references and explicit missing-field reasons. Include each target's capture/run references, receipt digest, counts, run IDs, exact step intervals, verification state and timing basis; summarize sources and entity contributions without double-counting targets. Convert timestamps to `America/New_York` using `pytz`, never a fixed offset. Check arithmetic, inventory coverage and sensitive-content exclusion, then return the path.

At the deadline, finish from collected evidence and mark unresolved fields `unavailable` with the missing evidence and observation time. This is an evidence-complete report, not a claim that unavailable timings were measured. Do not extend discovery with recursive archive searches, historical-session consults or repeated readiness checks; further investigation is a separate task.

## Timing basis

- `active_command_seconds` requires retained `time -p` real values.
- `target_wall_seconds` requires first invocation start and final verified completion. If only Bookkeeping creation/completion times exist, call it `retained_run_span_seconds`, not target wall time.
- Step intervals are event intervals, not CPU time; their sum is not wall time.
- Initialization requires exact request and READY evidence. Missing endpoints stay unavailable; never substitute file modification times.
- Preserve raw timestamps and exact operation names. Report generation never resets, replays or starts production work for a sample.
