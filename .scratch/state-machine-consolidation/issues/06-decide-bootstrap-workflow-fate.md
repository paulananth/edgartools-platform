# 06 — Decide `bootstrap` (Warehouse Pipeline Machine) fate

Type: task

Status: resolved

## Question

`bootstrap` (edgartools-prod-bootstrap) is a Warehouse Pipeline Machine, not
an MDM Pipeline Machine -- outside this map's original destination (the
MDM-tail duplication across mdm-gold/ownership-mdm-gold/silver-mdm-gold/
bronze-seed-silver-gold/residual-holds-graph). Surfaced while producing a
State Machine Atlas diagram of the platform's Step Functions layout and
fielding a follow-up question comparing `bootstrap` to `daily-incremental`.
Decide whether `bootstrap` should be kept, partially decommissioned
(state machine only), or fully retired (state machine + CLI command).

## Live evidence (2026-09-02)

- Zero EventBridge rules trigger `bootstrap` (`aws events list-rules`,
  no match).
- Exactly **one** execution ever: `bootstrap-ticket03-verify-1785426021`,
  started 2026-07-30, SUCCEEDED -- a verification run, not production
  traffic (`aws stepfunctions list-executions --max-results 1000`,
  `length(executions)` == 1).
- `bootstrap` and `daily-incremental` share the **identical** Step
  Functions shape: both built by `write_warehouse_mdm_gold_definition`
  (RunWarehouseTask → Mastering → MdmBackfill → Publish → Publish
  Relationships → Reconcile → GoldRefresh). The only wiring difference was
  which CLI command `RunWarehouseTask` ran.
- The two commands' company-selection logic genuinely differs:
  `bootstrap` iterated every tracked company (`--tracking-status-filter`,
  default `active`) and pulled each one's `--recent-limit` (default 10)
  most recent filings, blind to whether anything changed.
  `daily-incremental` uses SEC's daily form index over a date range
  (default 7-day lookback) to discover exactly which CIKs filed something,
  loading only those -- genuinely incremental, not recency-capped.
  `daily-incremental` has an active Mon-Sat 08:00 ET schedule
  (`edgartools-prod-daily-incremental-refresh`) and is the real recurring
  job; it structurally supersedes `bootstrap` for ongoing use.
- Confirmed no hidden callers: `load_mode == "bootstrap"` (distinct from
  `"bootstrap_full"`) drove no downstream pipeline behavior anywhere in
  `warehouse_orchestrator.py` (only `"bootstrap_full"` is ever compared).
  `_resolve_bootstrap_target_ciks` (the CIK-selection helper `bootstrap`
  used) is shared with `bootstrap-full`/`targeted-resync` and stays.
  `workflow_command_expression()`/`workflow_cik_command_expression()`'s
  `bootstrap)` case arms were confirmed dead already -- their sole caller
  loop only iterates the 7 Single-Command Workflow Machine names, never
  `bootstrap`.

## Decision (user-confirmed via AskUserQuestion)

**Full retirement** -- delete both the state machine and the `bootstrap`
CLI subcommand entirely, not just the AWS-side registration.

## What was done

- `edgar_warehouse/cli.py`: removed the `bootstrap` argparse subcommand +
  `_handle_bootstrap`; simplified `_add_common_bootstrap_args` (dropped the
  now-single-caller `include_recent_limit` parameter and the `--recent-limit`
  flag it gated -- `bootstrap` was its only `True` caller).
- `edgar_warehouse/application/warehouse_orchestrator.py`: removed
  `"bootstrap"` from `SOURCE_EXPORT_COMMANDS`; removed the
  `command_name == "bootstrap"` dispatch block in the bronze-capture
  function; removed the matching branch in `_resolve_scope`.
- `edgar_warehouse/infrastructure/dataset_path_catalog.py`: removed
  `"bootstrap"` from `_DEFAULT_MANIFEST_COMMANDS`.
- `edgar_warehouse/infrastructure/warehouse_settings.py`: removed
  `"bootstrap"` from `SERVING_EXPORT_COMMANDS`.
- `infra/scripts/deploy-aws-application.sh`: removed the ~8-line
  `bootstrap` SFN registration block; removed the dead `bootstrap)` case
  arms in `command_task_profile()`, `workflow_command_expression()`, and
  `workflow_cik_command_expression()`; removed the `bootstrap)` case arm
  and `WAREHOUSE_COMMANDS` dict entry in `write_warehouse_mdm_gold_definition`
  -- **deliberately left the `case "$workflow_name" in ... esac` dispatch
  shape and the dict itself in place** rather than collapsing to a single
  hardcoded value (`/gof-refactor-reviewer` consult: the function has been
  touched in 10+ commits and is a demonstrably active extension point --
  collapsing it now would very likely need to be undone the next time a
  second warehouse-pipeline-shaped command is added). Updated ~7 now-stale
  comments describing "the bootstrap branch"/"shared bootstrap/
  daily_incremental case" that referenced code paths this removal made
  unreachable.
- `docs/runbook.md`: repointed the Step 6 example (which relied on
  `bootstrap-full`-only `--cik-list` support that `daily-incremental`
  doesn't have) to `bootstrap-full`; fixed an unrelated pre-existing bug
  found along the way (`./scripts/ops/trigger.sh bootstrap` never matched
  any real `trigger.sh` case label -- the load_history-recovery section
  meant `trigger.sh load-history`).
- `scripts/ops/trigger.sh`: repointed the `recent` shorthand from
  `edgartools-{env}-bootstrap` to `edgartools-{env}-daily-incremental`.
- `CLAUDE.md`: removed the `bootstrap` row from the "When to use what"
  table (dated 5-whys sections referencing `bootstrap` left untouched per
  this file's own convention); fixed the current/prescriptive Phased
  Pipeline note about `ResolveCompanyIdentityBounded`.
- `CONTEXT.md`: updated Warehouse Pipeline Machine's machine count (2 → 1)
  and, while there, **corrected a genuine error from this same map's
  ticket carried over from the earlier context-step-functions session**:
  the entry had attributed the wrong builder function
  (`build_workflow_states`, which actually belongs to the MDM Utility
  Machine's per-mode state construction, confirmed via its own
  `"Route to the named MDM Utility Machine mode"` comment) instead of the
  real one, `write_warehouse_mdm_gold_definition`.
- Full test suite green: 2947 passed, 6 skipped.
- Also found and removed while tracing the real CLI dispatch chain (a
  second, separate command-registry system this ticket hadn't originally
  scoped): `edgar_warehouse.application.command_router.run_command` (which
  `edgar_warehouse/runtime.py` re-exports, and which `cli.py` actually
  imports) routes through `LEGACY_COMMAND_REGISTRY` in
  `edgar_warehouse/application/commands/__init__.py`, not directly through
  `warehouse_orchestrator.run_command` -- both converge on the same
  `warehouse_orchestrator._execute_warehouse` engine, but `bootstrap` had
  its own thin wrapper chain in this second system too:
  `commands/__init__.py`'s `"bootstrap": bootstrap.execute` registry entry
  and `bootstrap` import, the `edgar_warehouse/application/commands/bootstrap.py`
  module itself (deleted), and `run_bootstrap()` in
  `edgar_warehouse/application/workflows/bronze_submissions_ingest.py`
  (deleted, zero other callers confirmed). Also corrected CLAUDE.md's Quick
  Navigation claim that `command_router.py` is "a compatibility shim
  re-exporting from [warehouse_orchestrator.py], not a separate
  implementation" -- it has its own real (if thin) `run_command`, confirmed
  false while tracing this chain.
- 3-axis code review (Standards/Spec/GoF) run before commit, per CLAUDE.md's
  hard rule. Standards: 2 findings, both about this ticket file's own
  Status/heading format not matching `docs/agents/issue-tracker.md`'s
  convention (fixed -- `Status: claimed` now, `## Answer` heading to follow
  on actual resolution). GoF: 1 finding, a dangling docstring reference in
  `tests/architecture/test_run_warehouse_task_profile_routing.py` pointing
  at the deleted seed-universe-routing test file, plus a related
  pre-existing factual error in the same docstrings (falsely claiming
  `daily_incremental` calls `command_task_profile('seed-universe')` --
  `deploy-aws-application.sh`'s own comment says the opposite; that call is
  gated on `workflow_name != "daily_incremental"`) -- both fixed. Spec: 2
  findings -- (1) a **third command-classification registry**,
  `edgar_warehouse/domain/policy/command_scope.py`'s `sync_mode_for_command()`
  and `sync_scope_type_for_command()`, still tested
  `command_name in {"bootstrap-full", "bootstrap", "bootstrap-batch"}` --
  exactly the "removed from one registry, missed a sibling" pattern
  CLAUDE.md itself calls out repeatedly (`ShardedSilverReader._TABLES`,
  etc.); fixed, `bootstrap` removed from both sets, no test coverage
  exists for either function so nothing else needed updating. (2)
  `scripts/ops/trigger.sh`'s `recent` shorthand INPUT changed
  `'{}'` → `'{"refresh_mode": "daily"}'` alongside the target-machine
  repoint -- correct (matches the real `edgartools-prod-daily-incremental-refresh`
  EventBridge rule's actual payload, confirmed live earlier this session
  via `aws events list-targets-by-rule`) but wasn't called out in this
  ticket's own narrative until now -- noting it explicitly here rather than
  leaving it an undocumented side effect.
- Merged as PR #530 (`598195d4`). Warehouse image rebuilt/pushed/verified
  (`sha256:b255c10f...` -- confirmed `bootstrap` absent from
  `build_parser()`'s subcommand choices) and deployed to prod via
  `deploy-aws-application.sh`; confirmed the generated
  `infra/aws-prod-application.json` manifest has zero `"bootstrap"`
  references in `state_machines`. Rollback snapshot of the live
  `edgartools-prod-bootstrap` definition captured to
  `.scratch/state-machine-consolidation/rollback-snapshots/edgartools-prod-bootstrap-2026-09-02.json`,
  then the state machine explicitly deleted via
  `aws stepfunctions delete-state-machine` (confirmed `status: DELETING`
  immediately after).

## Answer

Full retirement, executed exactly as decided: CLI subcommand, dispatch
branches, three separate command-classification registries, a second
undocumented dispatch chain (command_router.py), AWS Step Functions
registration, and the live state machine itself are all gone.
`daily-incremental` is now the sole Warehouse Pipeline Machine. Full test
suite green throughout (2947 passed, 6 skipped); 3-axis code review found
and fixed 5 real issues across all three axes before merge. See "What was
done" above for the complete change list and review findings.

## Deliverable

- [x] Live evidence gathered and confirmed (schedule, execution count,
      shared shape, no hidden callers)
- [x] User decision captured (full retirement)
- [x] Code removed across cli.py, warehouse_orchestrator.py,
      dataset_path_catalog.py, warehouse_settings.py,
      deploy-aws-application.sh, the second command-registry chain
      (commands/__init__.py, commands/bootstrap.py, bronze_submissions_ingest.py),
      and a third registry found by the Spec review
      (domain/policy/command_scope.py)
- [x] Docs updated (CLAUDE.md, CONTEXT.md, docs/runbook.md,
      scripts/ops/trigger.sh)
- [x] Full test suite green
- [x] 3-axis code review (Standards/Spec/GoF) before commit -- all three
      done, all findings fixed
- [x] Rollback snapshot + explicit AWS state machine deletion
- [ ] Rollback snapshot + explicit AWS state machine deletion
