---
phase: 07
plan: 04
subsystem: mdm-generation-builder
tags: [mdm, postgres, step-functions, content-addressing, fan-out, fan-in]
requires: [07-02, 07-03]
provides: [generation-partition-planning, content-addressed-reuse, fan-in-verification, generation-build-state-machine]
affects: [07-05]
key-files:
  created:
    - edgar_warehouse/mdm/migrations/009_graph_generation_builder.sql
    - edgar_warehouse/mdm/generation.py
    - tests/mdm/test_graph_generation_builder.py
    - tests/architecture/test_aws_application_deploy.py
  modified:
    - edgar_warehouse/mdm/database.py
    - edgar_warehouse/mdm/migrations/runtime.py
    - edgar_warehouse/mdm/cli.py
    - infra/scripts/deploy-aws-application.sh
    - tests/mdm/test_runtime_ops.py
    - .planning/workstreams/fix-pipelines/REQUIREMENTS.md
key-decisions:
  - One partition per active node/relationship type by default; a caller-supplied
    `sharding={"TYPE": N}` map hash-shards (md5-mod, deterministic) any high-volume type
    into N partitions instead. Content address is
    (kind, type_name, shard_index, mdm_watermark, rule_version, schema_version,
    input_fingerprint) -> content_hash; reuse only fires on an exact match against a
    prior `built` (never `reused`) partition, so reuse chains can't compound drift.
  - committed_watermark is part of the content address, so two generations created at
    different instants never reuse each other by default -- this is intended (a
    generation is a frozen point-in-time snapshot), not a bug; tests pin a fixed
    watermark to isolate the "did content actually change" case from "did the clock
    move" case.
  - AWS orchestration (Step Functions Distributed Map for BuildPartitions) cannot thread
    generation_id through ecs:runTask.sync output (that integration returns the ECS task
    description, not container stdout), so GenerationPlan writes a small S3 side-channel
    manifest (generation.json + partitions.jsonl) keyed by the execution name, mirroring
    the existing cik_windows.jsonl convention load_history already uses for the same
    reason.
  - BuildPartitions tolerates 100% per-worker failure (ToleratedFailurePercentage=100):
    a single straggler partition must never abort the whole Map, because FanIn -- not
    the Map -- is the single authority that decides pass/fail for the generation. A
    partition failure inside generation-build-partition marks its own row 'failed'
    (via mark_partition_failed) before re-raising, so ECS/Step Functions still sees a
    real task failure for its own Retry/Catch bookkeeping.
  - Activate is only reachable via FanIn's success `Next`, never via FanIn's `Catch`
    (which routes to RetryFailedPartitions instead), and the CLI handler itself refuses
    to activate any generation whose status isn't already 'verified' -- a double guard
    (state-machine topology + CLI-side check) against ever activating an unverified
    generation.
  - generation_build is a standalone Step Functions workflow, not yet chained into
    load_history/bootstrap/daily_incremental -- those pipelines' read path still points
    at 07-05's future activation pointer, which doesn't exist yet. Wiring them in is
    07-05's scope.
requirements-completed: []
requirements-partially-addressed: [RSYNC-04]
completed: 2026-07-14
---

# Phase 7 Plan 04: Parallel Generation Builder, Partition Manifests, AWS Fan-Out/Fan-In

## Results

**Task 1 (partition planning/manifests/reuse/fan-in):**
- New `mdm_graph_generation` (one row per requested build: `status`
  `building`/`verified`/`activated`/`failed`, `committed_watermark`, `rule_version`,
  `schema_version`, `failure_reasons`) and `mdm_graph_partition` (one immutable,
  content-addressed row per node-type/relationship-type/shard: `content_hash`,
  `stable_key_hash`, `property_hash`, `status` `pending`/`building`/`built`/`reused`/
  `failed`, `reused_from_partition_id`) tables.
- `edgar_warehouse/mdm/generation.py`: `create_generation`, `plan_generation_partitions`
  (default 1 partition per active type, or N hash-sharded via `sharding=`),
  `build_partition`, `mark_partition_failed`, `retry_failed_partitions` (resets only
  `failed` rows; `built`/`reused` untouched), `fan_in_generation` (rejects
  missing/duplicate shards, mixed watermark/rule/schema version, endpoint gaps, any
  non-built/reused partition).

**Task 2 (AWS fan-out/fan-in orchestration, Terraform-passive):**
- New CLI commands (`edgar_warehouse/mdm/cli.py`): `mdm generation-plan --run-id
  --rule-version --schema-version [--shard TYPE:N]` (creates the generation, plans
  partitions, writes the S3 manifest); `mdm generation-build-partition --partition-id`
  (self-sufficient from partition_id alone; catches its own failure and calls
  `mark_partition_failed` before re-raising); `mdm generation-fan-in --run-id` (resolves
  generation_id from the S3 manifest, runs `fan_in_generation`, exit 1 on failure so
  Step Functions Catch engages); `mdm generation-retry-failed-partitions --run-id`; `mdm
  generation-activate --run-id` (refuses with `RuntimeError` unless
  `generation.status == "verified"`).
- New `write_generation_build_definition()` in `infra/scripts/deploy-aws-application.sh`,
  registered as the standalone `generation_build` Step Functions state machine (created
  only when `--enable-mdm`): `RuleVersionCheck`/`Default` and
  `SchemaVersionCheck`/`Default` (same `{}`-is-a-valid-trigger-input D-15 pattern as
  `load_history`) -> `GenerationPlan` -> `BuildPartitions` (DISTRIBUTED Map,
  `MaxConcurrency` from new `--mdm-generation-partition-concurrency`, default 8,
  `ItemReader` over the S3 `partitions.jsonl` manifest) -> `FanIn` -> `Activate` or (via
  FanIn's `Catch`) `RetryFailedPartitions`.
- New `tests/architecture/test_aws_application_deploy.py` (13 tests, same
  extract-the-real-bash-function-and-execute-it convention as
  `test_load_history_state_machine.py`): Distributed Map + bounded concurrency, S3
  manifest reader shape, per-partition command needs only `partition_id`, Retry
  configured, Activate reachable only via FanIn's success path (never bypassed, never
  via Catch), FanIn failure routes to `RetryFailedPartitions` and never to `Activate`,
  `{}` backward-compatible defaults, and passive Terraform confirmed to gain no new
  `generation_build`/`generation-plan`/`mdm_graph_generation` references.
- New `TestConcurrentGenerationsNotBlocked` class in
  `tests/mdm/test_graph_generation_builder.py` (3 tests): a second generation can open
  while the first is still `building` (no singleton constraint blocks it),
  `request_publication` succeeds regardless of generation status (the 07-03 outbox is
  fully decoupled from the generation builder), and the activation guard's condition
  is exercised directly.

## Deviations from Plan

**[Rule 3 - Scope] No pre-existing S3-manifest/path-template abstraction was extended.**
The plan's declared `files_modified` for Task 2 (`cli.py`, `snowflake_graph.py`,
`deploy-aws-application.sh`, test files) doesn't include
`edgar_warehouse/infrastructure/dataset_path_catalog.py`, which owns the codebase's
existing named-path-template system for S3 manifests like `cik_windows.jsonl`. Extending
that system would have required editing its YAML-backed template registry (out of this
plan's scope). Instead, the new CLI handlers use the already-generic
`edgar_warehouse.infrastructure.object_storage.StorageLocation` (S3-or-local, no
template registration needed) directly, reading the bucket root from the existing
`WAREHOUSE_BRONZE_ROOT` env var. Verified end-to-end with a manual round-trip (plan ->
manifest write -> build -> fan-in -> activate-refused-then-succeeds) against a local
filesystem root before committing.

**[Rule 3 - Scope] `snowflake_graph.py` was not modified in this plan**, despite being
listed in the plan's `files_modified`. 07-02 already added the `relationship_coverage`
optional parameter to `_named_relationship_parity_checks` that this plan's `files_modified`
list appears to have anticipated; Task 2's actual `<action>` text (ECS command payloads +
Distributed Map + Terraform-passive orchestration) has no further `snowflake_graph.py`
surface to touch, since `build_partition` in this plan intentionally stops at MDM-side
manifest bookkeeping (module docstring: "Building a partition's actual Snowflake rows is
out of this module's scope"). Not touching it is correct, not an omission.

## Verification

```text
uv run pytest tests/architecture/test_aws_application_deploy.py tests/mdm/test_graph_generation_builder.py -q
36 passed

uv run pytest tests/ -q --ignore=tests/architecture/test_load_history_state_machine.py
698 passed
```

## Self-Check: PASSED

RSYNC-04 partially addressed: partition planning/content-addressed reuse/fan-in
verification (MDM-side, Task 1) plus AWS fan-out/fan-in orchestration with bounded
concurrency, per-partition retry, and activation gated strictly on fan-in success
(Task 2) are both complete and regression-tested. Not done, and explicitly deferred to
07-05: the real per-partition Snowflake row write and the guarded Snowflake activation
pointer `Activate` will flip once that scope lands; `generation_build` is also not yet
chained into `load_history`/`bootstrap`/`daily_incremental`. Plan 07-05 (Snowflake
active-generation boundary/atomic activation) may begin.
