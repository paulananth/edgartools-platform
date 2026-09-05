Type: task
Status: open

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
