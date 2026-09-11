Type: task
Status: done

## Task

Build `infra/scripts/pipeline_stage_helpers.py`, a new sibling module next to
`deploy-aws-application.sh`, following `mdm_tail_helper.py`'s exact
`sys.path.insert(0, SCRIPT_DIR)`-importable convention (both heredocs will
import it the same way in Tickets 02/03). Prove it in isolation, with no
dependency yet on the real heredocs or the deploy script.

Contents:

- A private `EcsNetworkContext` (NamedTuple: `cluster_arn`, `subnets`,
  `security_groups`, `container_name`) bundling the four network params both
  public functions need, since neither can close over a heredoc's local
  variables the way the file's 7 existing per-heredoc `ecs_state()` closures
  do.
- A private `_ecs_state(network: EcsNetworkContext, task_def_arn, cmd_expr,
  next_state=None, is_end=False, retry_secs=120)` mirroring the shape of the
  file's existing local `ecs_state()` closures, but parameter-explicit
  instead of closure-capturing.
- `fundamentals_mode_stage(mode, task_arn, *, windowed, bronze_bucket_name,
  next_on_success, catch_next, network, map_comment=None,
  tolerated_failure_percentage=15, max_concurrency=1)` — `windowed=True`
  returns a Map+ItemReader+ItemProcessor+Catch dict (matching
  `load_history`'s 3 existing blocks); `windowed=False` returns a plain
  `_ecs_state` dict with the same mode/args baked in (matching what
  `daily_incremental`'s future fundamentals wiring needs). The CIK-window
  `ItemReader` key expression (`warehouse/bronze/reference/cik_universe/runs/
  {}/cik_windows.jsonl` formatted with `$$.Execution.Name`) is hardcoded
  inside the windowed branch, not a parameter — it has never varied across
  any of the 3 existing call sites. Returns `{state_name: state_dict}`, keyed
  the same way `wire_mdm_tail` already does.
- `force_capable_fetch_stage(command, task_arn, *, choice_state_name,
  fetch_state_name, ingest_state_name, next_state_on_success,
  catch_next_state, network, bronze_bucket_name)` — builds the Choice +
  Fetch + FetchForced + Ingest 4-state dict, keyed by state name. The
  Force-check `Comment` text is generated from `fetch_state_name` inside the
  function (standardize on the fuller ADV wording — "...otherwise X (no
  --force), the normal path." — for both), not threaded in as a parameter;
  this is a deliberate, called-out text normalization with zero functional
  impact, not a silent behavior change.

## Acceptance criteria

- [ ] `infra/scripts/pipeline_stage_helpers.py` exists with the module
      contents above.
- [ ] `tests/unit/test_pipeline_stage_helpers.py` exists, following
      `tests/unit/test_mdm_tail_helper.py`'s import/testing convention
      (`sys.path.insert(0, str(REPO_ROOT / "infra" / "scripts"))`), covering
      both public functions' windowed/non-windowed (or force/non-force)
      branches, success-path wiring, and failure-path wiring in isolation.
- [ ] A second `/gof-refactor-reviewer` pass runs against the actual diff
      (not just this ticket's plan) before commit, per this repo's CLAUDE.md
      hard rule.
- [ ] Full 3-axis `/code-review` (Standards, Spec, GoF) runs before commit.

**Blocked by:** None — can start immediately.

## Answer

Built (commits `c4e437cc`, `5b913646`). All 4 acceptance criteria met:
`infra/scripts/pipeline_stage_helpers.py` + `tests/unit/test_pipeline_stage_helpers.py`
exist (24 unit tests, all passing); both functions verified byte-identical
against the real ADV-bulk trio and the real windowed entity-facts stage by
direct hand-reconstruction comparison, not just unit-test assertions. A
second `/gof-refactor-reviewer` pass and the full 3-axis `/code-review`
both ran against the actual diff and are recorded below.

Two literal-signature corrections versus this ticket's original draft,
both load-bearing and necessary, not deviations of convenience:
- `fundamentals_mode_stage` and `force_capable_fetch_stage` both gained an
  `outer_state_name` parameter this ticket's draft never named — a state
  dict has to be keyed by *something* in the machine's States dict, and
  the draft only specified `item_processor_state_name` (the separate,
  inner per-window task's own name). These are two genuinely distinct ASL
  state names in the real pipelines (e.g. `"FetchEntityFacts"` outer vs.
  `"RunFundamentalsEntityFacts"` inner) — the Spec review flagged this as
  a gap in the ticket's own text, not a real deviation.
- `catch_next` (draft) → `catch_next_state` (built) for clarity, since the
  parameter is a state name, not a Catch clause.

Two real findings surfaced and fixed before the second commit:
- The second `/gof-refactor-reviewer` pass caught `_ecs_state` hardcoding
  `MaxAttempts: 2` (copied from `mdm_tail_helper.py`'s nested-execution
  retry policy) when every real ECS-task call site this module replaces
  (`deploy-aws-application.sh:3079`/`4095`) uses `MaxAttempts: 3`. Fixed by
  making it a parameter defaulting to 3. Verifying that surfaced a related
  `ResultPath` default mismatch (the real closures at those two line
  numbers don't default it at all, unlike a different closure elsewhere in
  the file for an unrelated machine) — also fixed.
- The Standards axis of `/code-review` found an unused `Optional` import
  and a Duplicated Code smell (the same `Catch`/`ResultPath`
  post-processing repeated 4 times across both public functions) — both
  fixed; `_ecs_state` now takes optional `catch`/`result_path` kwargs.

Spec and GoF axes of `/code-review` had no blocking findings. Process
note: both review passes ran against the first commit rather than before
it, since these are brand-new files with no other diff mechanism to
review against pre-commit — findings were addressed in a follow-up commit
on the same branch, same effect as reviewing pre-commit for a change this
small.

Ready for [Ticket 02](02-migrate-load-history-onto-shared-builders.md) and
[Ticket 03](03-migrate-daily-incremental-onto-shared-builders.md), both
now unblocked.
