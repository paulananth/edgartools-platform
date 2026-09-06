Type: task
Status: partially resolved (2026-09-05) -- 4 of 5 retired; bronze_seed_silver_gold deferred

**Resolution (2026-09-05):** `silver_mdm_gold`, `bootstrap_full`,
`catch_up_daily_form_index`, and `load_daily_form_index_for_date` retired
end-to-end: rollback snapshots captured (and, for `load_daily_form_index_for_date`,
`describe-execution` evidence for both its historical ticket-29 runs) before
touching anything; a fresh `list-executions` re-check immediately before each
delete reconfirmed zero (or, for `load_daily_form_index_for_date`, unchanged
dry-run-only) executions; dispatch code removed from
`infra/scripts/deploy-aws-application.sh` (the standalone-loop membership,
`command_task_profile()`/`workflow_command_expression()`/
`workflow_cik_command_expression()` case arms, and `write_silver_mdm_gold_definition`
deleted outright); `BOOTSTRAP_BATCH_CONCURRENCY` env var/CLI flag removed
entirely once its one real consumer (`silver_mdm_gold`) was gone; CLAUDE.md
and CONTEXT.md updated; associated tests updated/deleted (see PR).

**Real regression caught during this pass, fixed before shipping:** `bootstrap-full`
was initially removed from `command_task_profile()` too, on the assumption its
only consumer was the retired standalone loop -- the full test suite caught
that `bootstrap-full` is a live `SOURCE_EXPORT_COMMANDS` member
(`edgar_warehouse/application/warehouse_orchestrator.py`) still resolved
through this exact function by
`tests/architecture/test_source_export_commands_task_sizing.py`, since it
still builds gold/Snowflake export in-process on direct invocation. Restored.

**`bronze_seed_silver_gold`'s default path deferred, not retired:** confirmed
live that `infra/scripts/install.sh` explicitly triggers it with
`{"batch_size": 100, "release_mode": false}` as its documented "canonical
one-click path for cold-starting or recovering an environment's silver/MDM/
gold from a bronze snapshot" -- directly contradicting this ticket's
"confirmed-unused" premise for that one machine. User decided (2026-09-05)
to defer this piece rather than retire-and-break or redesign install.sh in
the same pass. A follow-up ticket is needed to decide bronze_seed_silver_gold's
actual fate before revisiting this.

**Also found, out of this ticket's scope, not fixed:** `edgartools-prod-mdm-gold`
is a live AWS orphan -- confirmed zero executions and zero remaining code
references (its writer function and dispatch were already removed by an
earlier ticket), but the AWS state machine object itself was never deleted.
Needs its own cleanup pass (same rollback-snapshot-then-delete pattern).

**Spawned by:** [Ticket 08 — Decide fate of MDM Pipeline Machine heads](08-decide-fate-of-mdm-pipeline-machine-heads.md)'s widened resolution (2026-09-05).

## Question

Not a decision — the decision is already made (Ticket 08). This is the
execution: retire 5 confirmed-superseded, confirmed-unused state machines
from the deployed application, following the same rollback-snapshot-then-
explicit-delete pattern already established by tickets 03, 04, and 06 in
this same map.

**Retire (delete the deployed state machine + its dispatch/registration
code):**

- `silver_mdm_gold` (`edgartools-prod-silver-mdm-gold`) — zero executions
  ever.
- `bronze_seed_silver_gold`'s **default path only**
  (`edgartools-prod-bronze-seed-silver-gold`) — its separate "strict
  release mode" branch stays untouched (Ticket 07's own prior decision,
  not reopened here). If the default and strict paths share a single
  deployed machine today, this ticket needs to first confirm whether
  retiring the default path means deleting the whole machine (if the
  strict path can be served some other way) or splitting the strict path
  out into its own standalone machine before removing the default one —
  check `write_bronze_seed_silver_gold_definition`'s actual structure
  before assuming either shape.
- `bootstrap-full` (`edgartools-prod-bootstrap-full`) — zero executions
  ever.
- `catch-up-daily-form-index` (`edgartools-prod-catch-up-daily-form-index`)
  — zero executions ever.
- `load-daily-form-index-for-date`
  (`edgartools-prod-load-daily-form-index-for-date`) — 2 executions ever,
  both tied to one past ticket's dry run.

**Checklist per machine** (mirroring tickets 03/04/06's own pattern):

1. Capture a rollback snapshot of the machine's current deployed definition
   (`aws stepfunctions describe-state-machine --query definition`) before
   touching anything, saved under this map's `rollback-snapshots/`.
2. Confirm zero running/recently-completed executions immediately before
   deletion (a fresh `list-executions` check, not just this ticket's
   evidence, in case something changed between charting and execution).
3. Remove the CLI subcommand (if the machine's head has no other caller),
   the Step Functions definition-writer function/dispatch branch in
   `infra/scripts/deploy-aws-application.sh`, any command-classification
   registry entries (`SOURCE_EXPORT_COMMANDS`, `LEGACY_COMMAND_REGISTRY`,
   etc.), and the live AWS state machine itself.
4. Update `CONTEXT.md`'s domain glossary entries (`MDM Pipeline Machine`'s
   "Exactly 5 today" count, the `Warehouse Pipeline Machine`/`Load History
   Machine` entries if they reference any of these) and this map's own
   Destination/Notes if they still list these machines as live.
5. Update CLAUDE.md's "When to use what" table and Quick Navigation if
   either references any of these 5 by name.

**Done when:** all 5 machines are gone from `aws stepfunctions
list-state-machines`, their dispatch code is removed (not just the AWS
object), and `daily_incremental`/`load_history`/`targeted-resync`/
`load-daily-form-index-for-date`'s own removal-adjacent tests (if any
reference these names) are updated or removed to match.
