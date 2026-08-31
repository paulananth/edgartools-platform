# Add Per-Run Binding Columns to MDM Tables

Type: task
Status: resolved
Blocked by: none

## Question

Add a `run_id` (or `generation_id`, where a table already tracks graph
generations) column to MDM's Postgres/Snowflake-mirrored tables, so MDM
writes achieve the same per-run bindability that Snowflake-native chains
already have.

Raised by [Decide the Execution and Loop Telemetry Contract](17-decide-execution-and-loop-telemetry-contract.md).
Ticket 11's gate 3 confirmed this asymmetry directly: chain G (`gold`) and
chain T (`ticker`) bind cleanly to a specific execution via
`SNOWFLAKE_REFRESH_STATUS`, matching row/table counts and timing — chain M
(MDM) is live and non-stale but **not individually bindable in Snowflake at
all**, because no MDM table carries a per-run tracking column. This forced
every MDM-relationship-count question in Tickets 12/13 to fall back to
CloudWatch structured logs (7-day retention) or be marked unreconstructable
outright once those logs expired.

Schema work on live Postgres and its Snowflake mirror, not a logging or
manifest change — split out from Ticket 17 specifically because of that
scope difference. Determine which MDM tables need the column (starting
point: `mdm_relationship_instance`, per Tickets 12/13's repeated need to
bind relationship-type insert counts to a specific backfill run), whether
it's a nullable additive migration or requires backfilling existing rows,
and how it threads through to the existing Snowflake mirror
(`infra/scripts/generate_mdm_mirror_ddl.py`, per CLAUDE.md's "MDM Snowflake
mirror schema lost on cutover" incident) so the new column survives future
schema regenerations.

## Resolution (2026-08-31)

Adopted the [MDM Run Identity ADR](../../../docs/adr/0007-bind-mdm-commit-evidence-to-originating-run.md):
only durable entity-change and relationship-version evidence carries the
originating operation identity. `mdm_change_log` and
`mdm_relationship_instance` now have nullable, partially indexed `run_id`
columns. Migration `019_mdm_run_identity.sql` upgrades existing Postgres
tables additively; historical rows remain `NULL`, no current-state table gains
the field, and there is no speculative backfill.

All evidence-producing CLI and generated Step Functions paths bind one
operation identity, worker pipelines reuse it, manual mutations generate or
accept one, and idempotent relationship reruns preserve the first version's
origin. Export includes the stored value without replacing it. The generated
and checked-in Snowflake mirror DDL both contain the columns plus guarded
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` upgrades for existing mirrors.

Verification after rebasing on current `origin/main`: 246 focused MDM and
architecture tests passed; targeted new-boundary Ruff and mypy checks passed;
the full suite reached 2,874 passed, 7 skipped, and 35 subtests passed. Its
eight failures are the existing acquisition/conflict Postgres cluster caused
by the baseline test schema lacking `captured_etag` and
`captured_last_modified`; Ticket 30 does not touch those paths. The two-axis
Standards/Spec review is clean after narrowing `CONTEXT.md` to the implemented
commit-evidence-producing-stage contract. No production schema or workflow
was deployed.
