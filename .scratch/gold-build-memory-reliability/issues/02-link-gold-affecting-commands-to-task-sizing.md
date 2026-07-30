# Link GOLD_AFFECTING_COMMANDS membership to required task-profile sizing

Type: task
Status: resolved

## Question

`GOLD_AFFECTING_COMMANDS` (`edgar_warehouse/application/warehouse_orchestrator.py:81-91`, 7
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

## Answer

Went with **option 2** (architecture test) — cheaper and lower-risk than restructuring
`deploy-aws-application.sh` (a 2000+-line bash script with no test harness beyond the
JSON-generation checks already in `tests/architecture/`) into a single source of truth, and
the ticket itself said either was acceptable.

New file: `tests/architecture/test_gold_affecting_commands_task_sizing.py`. Mirrors this
repo's existing convention (`test_daily_incremental_state_machine.py`) of invoking the real
bash `workflow_profile()` function via subprocess rather than hand-duplicating its
case-statement logic in a Python regex — so the test can't silently drift from the actual
script. For each `GOLD_AFFECTING_COMMANDS` member it resolves the real task memory (via
`workflow_profile()` + the `register_task_definition` calls' literal cpu/memory args) and
asserts it meets `GOLD_BUILD_MEMORY_FLOOR_MB` (4096 today — the actual current minimum, not
an aspirational value; ticket 03 is where that floor should actually be raised).

**A genuinely new finding surfaced while building this**, beyond what the ticket text
assumed: `bootstrap-next` (a `GOLD_AFFECTING_COMMANDS` member) is **never** passed to
`workflow_profile()` at all — there is no `bootstrap_next` case in the function and no
standalone `bootstrap_next` state machine. It only ever runs inside `load_history`'s windowed
Step Function, where its task definition ARN is hardcoded directly
(`write_load_history_definition`'s `wh_task_medium_arn` parameter, "per-window
bootstrap-next/-fundamentals") — completely bypassing the case-statement mechanism the rest of
`GOLD_AFFECTING_COMMANDS` goes through. A test that only checked `workflow_profile()`
coverage would have missed this entirely. Documented as an explicit, commented exception
(`_SPECIAL_CASED_MEMORY_MB`) rather than silently special-cased — if a future session adds
another out-of-band-wired command, the test fails loudly and points at this allowlist instead
of passing by accident.

Verified the guard actually works: temporarily removed the `bootstrap-next` allowlist entry
and confirmed all 8 tests fail with a clear message; restored and confirmed green again
(diff-clean against the pre-edit file). Full suite: `uv run python -m pytest tests/unit
tests/architecture -q` still green after this addition (see PR for exact count).

Not fixed here (correctly out of scope per the ticket): the actual under-provisioning itself
(`daily-incremental`/`bootstrap`/`full-reconcile`/`gold-refresh` still resolve to `medium`,
whose memory is numerically identical to `large` today) — that's ticket 03's job. This
ticket's job was only to make future drift loud, which it now does.

**Second finding, directly relevant to ticket 03's question 1 — `gold-refresh` itself runs on
two different profiles depending on which Step Function invokes it.** The standalone
`edgartools-prod-gold-refresh` state machine (built via the `workflow_profile()`-driven loop at
`deploy-aws-application.sh:3098`) resolves `gold_refresh` → `medium`, exactly as this test
checks. But every composite pipeline that embeds a final gold-refresh step as its own stage —
`load_history`, `mdm_gold`, `ownership_mdm_gold`, `residual_holds_graph`, `silver_mdm_gold`,
`bronze_seed_silver_gold`, `generation_build` — hardcodes that step directly to `wh_large_arn`
("full-universe DuckDB is multi-GB"), completely bypassing `workflow_profile()`. So today, by
coincidence (`medium`==`large`==4096MB), all of these are equally provisioned; but if ticket 03
resolves its question 1 as "raise `large`'s memory, not `medium`'s," the composite pipelines'
embedded gold-refresh steps get the fix and the **standalone** `gold-refresh` Step Function does
not — it would stay on `medium` and remain exactly as exposed as `daily_incremental` was.

**Caveat on this test's actual coverage, stated honestly rather than left implicit:** this
architecture test only validates the `workflow_profile()`-driven dispatch path (the standalone
per-command state machines). It does **not** inspect the composite pipelines' embedded
`wh_large_arn`/`wh_medium_arn` direct-wiring — those aren't parsed or asserted on at all. They
happen to all use `wh_large_arn` for gold-refresh today, so they're not currently at risk, but a
future edit repointing one of those embedded steps to `wh_medium_arn` would not be caught by
this guard. Not fixed here — flagged in the map's fog as a known gap in this ticket's coverage,
sharp enough to become its own ticket if it ever needs fixing.
