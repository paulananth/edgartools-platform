# Remove legacy tables and their code

Type: task
Status: 2a merged (#764); 2b/2c in review (Claude, branch `claude/remove-legacy-2bc-scripts-dbt`)

## Operator ruling

- Asked how far to go, the operator chose "Everything not reachable"
  (2026-09-30): delete every module the enabled commands cannot reach.
- For AWS, the operator chose "Code only (Recommended)" (2026-09-30): delete
  the dead deploy and ops scripts and their tests; leave the Terraform files
  and everything live in AWS. Tearing down the live schedules and state
  machines is a separate ticket, done only on the operator's word.

## 2a: done

- **The CLI.** `edgar_warehouse/cli.py` offers five commands: `rules`,
  `bookkeeping`, `change-journal`, `mdm` and `resolve-snowflake-env`. The
  legacy command stack (`runtime` → `command_router` →
  `warehouse_orchestrator`) is no longer imported.
- **`mdm` has five subcommands, all Clean MDM:** `migrate`,
  `check-connectivity` (new, reads `mdm_v2.migration`), `counts`,
  `prepare-clean-company`, `name-census`.
- **The run coordinator** keeps its run in MDM: migration 043 adds
  `mdm_v2.run`, written only by `start_run`/`finish_run`. It no longer uses
  the retired Bookkeeping `pipeline_run`, as the GoF consult recommended.
  Test: `tests/integration/test_clean_run_postgres.py` (5 tests, one on a
  store populated before 043).
- **Deleted:**
  - every `edgar_warehouse` module the entry points do not reach. The entry
    points are the CLI, all of `mdm/clean`, the two skill scripts and the
    two provisioning scripts. That is 219 modules, found by walking every
    import, including those inside functions;
  - legacy MDM migrations 001–022 and `edgar_warehouse/config`;
  - 170 test files that tested the deleted code;
  - 3 legacy graph ops scripts.
  Kept, because the Snowflake Streamlit dashboard imports them:
  `serving/dashboard_modes.py`, `dashboard_query_registry.py`,
  `dashboard_workflows.py`.
- **Moved.** `SnowflakeConnectionSettings` moved to
  `edgar_warehouse/snowflake_settings.py`.

## Review (three axes)

- **Standards:** two judgement findings, both fixed.
  - The grant loop skipped any missing function; it now skips only a
    function whose migration is deliberately not applied
    (`FUNCTION_MIGRATION`).
  - Two concurrent reconciles could set a succeeded run back to running.
    `finish_run` now takes the run's lock, and a succeeded run stays
    succeeded.
  - Also: the coordinator module is renamed `mdm/clean/run.py`, and stale
    text was moved out of the Snowflake settings module.
- **Spec:** fixed three things.
  - A changed scope raises `Conflict` again, as before.
  - Stale docs are corrected (`AGENTS.md`, `local-operations.md`,
    `evidence.md`).
  - The 05 Proving Run script uses the new coordinator.
  Noted rather than changed: a 1 MiB cap on a run's scope, new with 043.
- **GoF:** each `mdm` command was dispatched twice, and the two lists had
  drifted (a dead `correction-batch` branch). Each subcommand is now bound
  to its own function, and `handle()` is gone. Test:
  `tests/unit/test_mdm_cli_commands.py`.

## Tests

Local runs, each under 5 minutes:

| Group | Result |
|---|---|
| Everything without a database | 1,214 passed |
| Clean MDM database tests | 106 passed, 1 xfailed |
| `test_clean_mdm_postgres.py` and `test_configured_bookkeeping_postgres.py` | 91 passed |
| `test_clean_per_kind_views.py`, after fixing its path to the SQL folder | 12 passed |
| The rest of `tests/integration` | passed, apart from the 3 removed ops-script tests |

## 2b and 2c: checklist

- [x] Inventory: every script, workflow, doc and test that calls a deleted
  command or imports a deleted module. Every Step Functions command the AWS
  deploy script built was deleted in 2a, except `mdm check-connectivity` and
  `counts` (2026-09-30 20:40 ET)
- [x] Operator ruling on AWS scope: "Code only" (2026-09-30 20:45 ET)
- [x] GoF consult: deletions sound; one correctness finding in
  `bootstrap-prod-mdm.sh` (below) (2026-09-30 20:50 ET)
- [x] Deleted the dead AWS pipeline code: `deploy-aws-application.sh`,
  `run-aws-mdm-e2e.sh`, `mdm_tail_helper.py`, `pipeline_stage_helpers.py`,
  the Neo4j e2e, Mongo decision and mirror-generator scripts, the cutover
  audit, `load_local_silver_landing.py`, `reclaim-warehouse-duplicates.sh`,
  `remove-aws-mdm-rds-after-cutover.sh`, `test-bootstrap-idempotency.sh`,
  `scripts/run-bootstrap.sh`, `scripts/verify-pr1/`, 22 `scripts/ops`
  pipeline tools, 2 `scripts/test` pipeline smokes, the two AWS cost GitHub
  workflows, `examples/mdm_graph_dashboard/`, `infra/snowflake/mdm_dashboard/`,
  `edgar/ai/skills/platform/pipeline-setup.md`, `docs/aws-cost-optimizer.md`
  (2026-09-30 21:00 ET)
- [x] Deleted or trimmed the 12 test files that read them; the rest of
  `tests/architecture` + `tests/unit` pass (643 passed, 2026-09-30 20:58 ET)
- [x] Kept: `install-neo4j-graph-app.sh` and the installer's mirror + graph
  schema stage, because the live dashboard reads `NEO4J_GRAPH_MIGRATION`
  (`serving/dashboard_workflows.py`); `09_mdm_mirror_schema.sql` stays with
  that stage, its header now saying it is a frozen snapshot that nothing in
  the kept code reads
- [x] `bootstrap-prod-mdm.sh`: no longer hands ownership of every MDM table
  to `application` (an owner bypasses Clean MDM's grants) or grants DML on
  `public`; its connectivity check reads the new one-line report. Verified
  on real CLI output (2026-09-30 21:12 ET)
- [x] `install.sh`: dropped the ECS task-definitions stage and the dead
  application-summary check, kept only the ECR-cleanup note, and runs
  `mdm migrate` before `mdm check-connectivity`. `test_install_wizard.py`:
  33 passed (2026-09-30 21:05 ET)
- [x] Messages in `create-deployer.sh`, `bootstrap-aws-mdm-secrets.sh`,
  `cleanup-ecr-images.sh` and `infra/snowflake/streamlit/deploy.sh`
- [x] Docs that tell someone to run something: `AGENTS.md`, `README.md`,
  `CLAUDE.md`, `docs/runbook.md`, `docs/aws-authentication.md`,
  `infra/terraform/README.md`, `docs/prodb-to-prod-promotion.md`,
  `docs/specs/clean-mdm/local-operations.md`, the Change Journal skill; a
  "Retired" banner on five docs that describe the old pipeline. Dated
  handoffs and research notes are left as history
- [x] dbt: no model changed. `company` and `mdm_company` read
  `MDM_COMPANY_ENTITY`, which keeps its last rows; retiring them would break
  the live dashboard, and pointing them at Clean MDM needs a Clean
  MDM-to-Snowflake export that does not exist. The source description now
  says so (2026-09-30 21:10 ET)
- [x] 2c: a fresh PostgreSQL 16 migrated from zero holds only `mdm_v2`
  (54 tables and views, 20 migrations), zero `public.mdm_*` tables, no
  `mdm_v2` table owned by `application`; `mdm check-connectivity` works as
  the runtime role. Container stopped (2026-09-30 21:13 ET)
- [ ] ~~Recreate the operator's `edgartools-clean-mdm-pg16` without legacy
  tables~~ deferred to slice 3: it is recreated once, under the renamed
  schema, only on the operator's word
- [ ] ~~Drop legacy tables in the hosted Snowflake Postgres MDM~~ deferred:
  only on the operator's word for that database
- [x] Three-axis `/code-review` (2026-09-30 21:19 ET):
  - **GoF:** leave it.
  - **Standards:** fixed the stale header line in `09_mdm_mirror_schema.sql`,
    the gateway docstring naming a deleted script, and leftover "this fix"
    wording in the installer; added a note to `docs/snowflake-cli-migration.md`.
    The stranded graph-review dashboard and Terraform comments are follow-ups.
  - **Spec:** fixed `TODOS.md` (note at the top), the installer's references
    to a stage that no longer exists, and the unsupported "the dashboard
    reads these tables" claim. Confirmed no `.tf` change and no live action;
    `bootstrap-prod-mdm.sh` matches `store.migrate`'s grant model.
- [ ] PR, CI green, merge on the operator's word

## Follow-ups found (not built here)

- The live `MDM_GRAPH_DASHBOARD` Streamlit app keeps running on the files
  already uploaded, but its source (`infra/snowflake/mdm_dashboard/`) is
  deleted, so it can no longer be redeployed, and its data
  (`MDM_GRAPH_REVIEW`) has no writer. Its Terraform module, grants SQL and
  `check-dashboard-acceptance.py` views still name it. Retire it in the
  teardown, on the operator's word.
- The two deleted GitHub workflows stopped a weekly AWS cost cron. Its
  Python was already deleted in 2a, so it could no longer have run.
- Terraform comments and output descriptions still say "created by
  deploy-aws-application.sh" (`warehouse_runtime/main.tf`, prod
  `outputs.tf`, `scheduled_*.tf`). Fix them in the teardown, since the
  ruling leaves Terraform untouched here.
- `docs/aws-mdm-snowflake-postgres-cutover.md` and
  `docs/prod-mdm-snowflake-graph-first-load.md` still name deleted scripts;
  both carry the "Retired" banner.
- Teardown of live AWS: the EventBridge schedules
  (`scheduled_daily_incremental.tf`, `scheduled_fence_monitor.tf`), the Step
  Functions state machines and ECS task definitions they start. They run
  deleted commands, so any run fails. Operator's word needed.
- A Clean MDM export to Snowflake, so gold `company` / `mdm_company` get new
  rows again.
- The four gold models whose source tables were written by deleted Python
  (`earnings_calendar`, `consensus_estimates`, `transcript_events`, and
  `guidance_facts`' upstream) get no new rows.
- `scripts/batch/` (edgartools smoke scripts) and the dashboard acceptance
  scripts are kept; they do not touch the retired pipeline.
