# Link GOLD_AFFECTING_COMMANDS membership to required task-profile sizing

Type: task
Status: open

## Question

`GOLD_AFFECTING_COMMANDS` (`edgar_warehouse/application/warehouse_orchestrator.py:81-91`, 6
members: `bootstrap-full`, `bootstrap-next`, `bootstrap`, `daily-incremental`,
`targeted-resync`, `full-reconcile`, `gold-refresh`) all call the identical memory-heavy
`build_gold()` path. Each workflow's ECS task profile is set independently in
`workflow_profile()` (`infra/scripts/deploy-aws-application.sh:970-983`), a separate file with
no link back to the set. Today `bootstrap_full` and `targeted_resync` are `large`;
`daily_incremental`, `bootstrap`, `full_reconcile`, `gold_refresh` are still `medium`.

This gap is exactly why `daily_incremental` reproduced an OOM that `gold-refresh` had already
hit and gotten a dedicated fix for (commit `37c3171`, "gold-refresh OOM — free PyArrow, stream
silver upload, large task", May 2026) — adding a new command to `GOLD_AFFECTING_COMMANDS`
silently inherits the memory risk with nothing flagging that its task profile needs revisiting
too.

Per this session's `/gof-refactor-reviewer` pass, this isn't a class-hierarchy pattern fix —
just make the two collections co-located or cross-checked so they can't drift silently again.
Options to consider (pick one, implement it):

1. A single source of truth — e.g. `workflow_profile()` derives its answer from
   `GOLD_AFFECTING_COMMANDS` membership plus an explicit exception list, rather than an
   unrelated per-workflow case statement.
2. A test (e.g. in `tests/architecture/`) asserting every `GOLD_AFFECTING_COMMANDS` member maps
   to at least the `large` profile in `deploy-aws-application.sh`, failing loudly if a new
   command is added to one without the other being updated.

Either is acceptable; pick whichever is cheaper to keep correct going forward. This is
independent of and can proceed in parallel with ticket 01 (the `build_gold` streaming fix) —
this ticket's job is preventing *future* commands from silently inheriting the same risk,
not fixing the current OOM's root cause.

Blocked by: none. Depends conceptually on ticket 03's outcome for what the "at least" memory
floor should actually be, but can be implemented against today's values and adjusted once
ticket 03 lands.
