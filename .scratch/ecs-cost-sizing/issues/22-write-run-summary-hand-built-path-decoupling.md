# WriteRunSummary Hand-Built S3 Path: Root Cause, Fix, and Portfolio-Wide Check

Type: research
Status: resolved
Blocked by: (none)

## Question

`load_history`'s `WriteRunSummary` state failed 4/4 retries on ticket 42's
`retry5` execution (a 30.5h full-universe backfill that completed all real
work but died on its terminal state) with "cik_windows.jsonl not found at S3
key". Root-cause the failure, fix it, and check whether the same
hand-built-path pattern exists anywhere else in the retained state-machine
portfolio this map is auditing -- since if it's a repeated shape, it belongs
in [Decide Step Functions Structural Simplification](18-decide-step-functions-structural-simplification.md)'s
scope, not just a one-off patch.

## Root cause

`WriteRunSummary`'s ASL (`infra/scripts/deploy-aws-application.sh`) built its
`--from-windows-key` argument via a literal
`States.Format('warehouse/bronze/reference/cik_universe/runs/{}/cik_windows.jsonl', ...)`.
`WAREHOUSE_BRONZE_ROOT` already includes the `warehouse/bronze` prefix, so
`context.bronze_root.join(from_windows_key)` in
`edgar_warehouse/application/warehouse_orchestrator.py` doubled it, producing
a key that could never resolve. The file existed exactly where
`ComputeWindows` had written it a day earlier -- confirmed live against S3
before writing the fix.

This was **not** the `ecs:runTask.sync` stdout-capture limitation this
portfolio already documents elsewhere (`generation_plan`'s comment at
`deploy-aws-application.sh:4302`: "ecs:runTask.sync does not surface
container stdout as state output" -- the reason `ComputeWindows`/
`GenerationPlan` publish an S3 side-channel file instead of threading values
through Step Functions state at all). That pattern is deliberate and correct
everywhere it's used, including here -- `WriteRunSummary` legitimately needs
to read the file `ComputeWindows` wrote via S3, not via state. The actual
defect was narrower: **the ASL re-derived a path template that a Python
resolver (`edgar_warehouse/infrastructure/dataset_path_catalog.py`'s
`WarehousePathResolver.cik_windows_path()`) already owned**, and the two
copies drifted out of sync. Proof the resolver was the correct source of
truth: two lines below the buggy code, the same handler already derived
`cik_snapshot.jsonl`'s path via `default_path_resolver().cik_snapshot_path(sync_run_id)`
-- correctly, with no prefix bug -- because `WriteRunSummary` already
receives `--run-id` and never needed the ASL to hand-build that key at all.

## Fix (already applied and verified live, not just proposed)

- `--from-windows-key` removed entirely from the CLI (`edgar_warehouse/cli.py`)
  and the ASL (`infra/scripts/deploy-aws-application.sh`) -- it had exactly
  one caller.
- The handler now derives the key itself via
  `default_path_resolver().cik_windows_path(sync_run_id)`, matching the
  sibling `cik_snapshot_path` call already in the same function.
- Full test suite green (`tests/unit`: 777 passed; `tests/architecture`: 403
  passed), `/gof-refactor-reviewer` pass: no structural concern, "leave it"
  for the rest of the handler.
- Shipped as two ordered prod actions, both confirmed live:
  1. A new warehouse image was built and pushed (this is a Python code
     change, not ASL-only -- the old image's `cli.py` still marked
     `--from-windows-key` `required=True`, so deploying the new ASL against
     the *old* image would have failed a different way; caught and corrected
     before declaring this done).
  2. `deploy-aws-application.sh --env prod` re-registered all 18 state
     machines against the new image. `describe-state-machine` on
     `edgartools-prod-load-history` confirms the live `WriteRunSummary`
     command is now `States.Array('write-run-summary', '--run-id',
     $$.Execution.Name)` -- no `--from-windows-key`, no doubled prefix.
- PR [#407](https://github.com/paulananth/edgartools-platform/pull/407)
  (merged to `main`).

## Portfolio-wide check: is this pattern repeated elsewhere?

Searched the full ASL generator (`infra/scripts/deploy-aws-application.sh`)
and `edgar_warehouse/` for other `States.Format(...)` calls that hand-build a
path matching one of `dataset_path_catalog.py`'s templates (grep for
`States.Format.*runs/{}` and cross-referenced every `--from-*-key`-shaped CLI
argument). **`--from-windows-key` was the only hand-built S3 path fed through
an ASL `States.Format` call in the whole portfolio.** Every other
S3-side-channel consumer (`GenerationPlan`/`BuildPartitions`,
`ComputeWindows`/`Stage1Parallel`'s `ItemReader` states) either reads via a
native Step Functions `ItemReader` (which correctly needs the full
bucket-relative key, a different and non-buggy contract -- see the code
comment added to the fix commit for why those are *not* the same bug) or
never re-derives a path the Python side already owns.

**Conclusion: this was a single, now-fixed defect, not a repeated shape.**
It does not need to feed into Ticket 18's structural-simplification scope as
a new pattern to fix elsewhere -- there is nowhere else to fix. Worth
carrying into Ticket 18 only as a general principle for any *new* ASL
generation code: hand-building a path in ASL that a Python resolver already
owns is a two-sources-of-truth risk regardless of whether it happens to be
buggy today.

## Answer

Root cause: an ASL literal duplicated a prefix already present in
`WAREHOUSE_BRONZE_ROOT`. Fixed by deleting the duplicate source of truth
(`--from-windows-key`) rather than patching the literal -- the handler now
derives its own path the same way its neighbor already did. Verified live in
prod (new image built, deployed, confirmed via `describe-state-machine`).
Portfolio-wide grep confirms this was an isolated defect, not a repeated
anti-pattern -- no other ticket needs to inherit this as a broader class of
work.

Separately (found while tracing `retry5`'s downstream effects, not part of
this ticket's original question): the same investigation surfaced that
`SNOWFLAKE_RUN_MANIFEST_TASK` had been `SUSPENDED_DUE_TO_ERRORS` since
2026-08-09 for an unrelated reason (a `TICKER_REFERENCE` MERGE key bug,
`infra/snowflake/sql/bootstrap/03_source_load_wrapper.sql`, keyed on `CIK`
alone when dual-class issuers like Alphabet legitimately need `(CIK,
TICKER)`). Also root-caused, fixed, and verified live (PR
[#408](https://github.com/paulananth/edgartools-platform/pull/408)) -- noted
here only because it was discovered in the same investigation, not because
it belongs to this map's scope; it's a Snowflake-side data-correctness bug,
not an ECS/Step Functions cost-sizing question.
