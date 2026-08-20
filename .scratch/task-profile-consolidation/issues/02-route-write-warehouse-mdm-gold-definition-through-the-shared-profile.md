# 02 — Route write_warehouse_mdm_gold_definition through the shared profile

**What to build:** `daily_incremental` and `bootstrap`'s `RunWarehouseTask`
ARN currently comes from hardcoded parameters inside
`write_warehouse_mdm_gold_definition` (`infra/scripts/deploy-aws-application.sh`,
~lines 3053–3850) — the exact gap that caused two real production OOM
incidents (`gold_refresh` in May 2026, `daily_incremental` in July 2026,
same root cause, missed twice because this function never consulted
`workflow_profile()`). Switch `write_warehouse_mdm_gold_definition` to
resolve every command's task profile from ticket 01's shared mapping instead
of its own hardcoded params.

**Blocked by:** 01

**Status:** resolved (2026-08-19)

- [x] `write_warehouse_mdm_gold_definition` resolves task profile via the
      shared mapping from ticket 01 for every command it handles, not
      hardcoded `wh_task_large_arn`/`wh_task_medium_arn` parameters
- [x] Generated ASL for `daily_incremental` and `bootstrap` references the
      task-definition ARN the shared mapping specifies
- [x] Deploying (or a dry-run generation of) the state machine definitions
      produces byte-identical ASL to before this change for every other
      command already handled correctly today (no regression for commands
      that weren't part of the original bug)

## Answer

**Scope decision:** "every command it handles" is read as the two commands
this function is *parameterized by and invoked for* — `bootstrap` and
`daily-incremental`'s own `RunWarehouseTask` step (the exact step that
OOM'd twice in prod) — not every internal auxiliary state inside the same
generated state machine (`backfill-mdm-entity-ids`, `gold-refresh`,
`acquire-sec-fetch-lease`, `release-sec-fetch-lease`). Those four aren't
part of the original incident, aren't in ticket 01's mapping, and the
ticket's own acceptance criteria only ever name `daily_incremental`/
`bootstrap`'s ASL specifically. Migrating them was out of scope here; they
continue receiving their ARN via this function's existing
`wh_task_medium_arn`/`wh_task_large_arn` parameters, unchanged.

**Built:** `write_warehouse_mdm_gold_definition`
(`infra/scripts/deploy-aws-application.sh`) now resolves `RunWarehouseTask`'s
profile via `command_task_profile()`, called internally in bash right after
the function's parameter declarations. `workflow_name` (the underscore
Step-Functions spelling, `"bootstrap"`/`"daily_incremental"`) is translated
to the real hyphenated CLI command name via a small bash `case` (mirroring
the `WAREHOUSE_COMMANDS` dict already inside the python heredoc — kept
separate since bash and the embedded python are different processes), then
`command_task_profile()`'s answer is mapped to this function's own existing
`wh_task_medium_arn`/`wh_task_large_arn` parameters — no new public
parameter, no dependency on `task_definition_for_profile()`/the
`TASK_DEF_*_ARN` globals. The resolved ARN (`run_wh_task_arn`) is threaded
into the python3 heredoc as one additional argv value, and `run_wh`'s
`ecs_state(...)` call now uses it instead of the direct `wh_large_arn`
reference.

**Proof this is a genuine routing change, not a coincidental value match:**
new dedicated test file
`tests/architecture/test_run_warehouse_task_profile_routing.py`, mirroring
ticket 03's `test_bootstrap_next_task_profile_routing.py` technique exactly
— sources `command_task_profile()`'s real definition and then *redefines
it with a stub* immediately before invoking
`write_warehouse_mdm_gold_definition` (bash resolves function calls at call
time, so the later definition genuinely intercepts what the function calls
at runtime). Parametrized over both `bootstrap` and `daily_incremental`:
one test stubs `command_task_profile` to answer `"medium"` for the real
command name and asserts `RunWarehouseTask`'s `TaskDefinition` flips to the
medium ARN; another stubs it to `fail` on any command name other than the
exact real hyphenated string (`"bootstrap"`/`"daily-incremental"`) and
asserts generation still succeeds; a third confirms the unstubbed, real
value still resolves to `large`.

**Byte-identical ASL, verified analytically for both workflows:** generated
`write_warehouse_mdm_gold_definition`'s full JSON for both `bootstrap` and
`daily_incremental` from the commit immediately before this change and from
the current working tree (identical fake ARNs both times), and diffed —
`json.dumps(..., sort_keys=True)` output was byte-for-byte identical for
both. Zero behavioral change to either deployed state machine; only the
*source* of the `RunWarehouseTask` ARN decision moved.

**Existing tests updated to source the new internal dependency:** every
test that extracts and sources `write_warehouse_mdm_gold_definition`'s
source in isolation now also extracts+sources `command_task_profile()`
first (bash function resolution requires the callee to be defined in the
same subprocess): `test_daily_incremental_state_machine.py`,
`test_daily_identity_refresh_state_machine.py`,
`test_task_profile_source_of_truth.py`'s `_run_warehouse_task_profile`, and
`test_source_export_commands_task_sizing.py`'s helper of the same name. All
their tests still pass.

**Full suite:** `tests/architecture/` green — 498 passed, plus the 2
pre-existing, already-documented, unrelated
`test_bootstrap_dbt_snowflake_secret.py` failures. (An earlier full-repo
background run raced against this implementation's in-progress edits and
showed 12 stale failures mid-edit — re-ran clean once the edit completed;
not a real regression, noted here so the transcript isn't confusing.)
