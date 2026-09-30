# Remove legacy tables and their code

Type: task
Status: 2a in review (Claude, branch `claude/remove-legacy-2a-cli-and-mdm`)

## Operator ruling

- Asked how far to go, the operator chose "Everything not reachable"
  (2026-09-30): delete every module the enabled commands cannot reach.

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

## Tests

Local runs, each under 5 minutes:

| Group | Result |
|---|---|
| Everything without a database | 1,214 passed |
| Clean MDM database tests | 106 passed, 1 xfailed |
| `test_clean_mdm_postgres.py` and `test_configured_bookkeeping_postgres.py` | 91 passed |
| `test_clean_per_kind_views.py`, after fixing its path to the SQL folder | 12 passed |
| The rest of `tests/integration` | passed, apart from the 3 removed ops-script tests |

## 2b and 2c: next

- **Non-Python dependents:**
  - `infra/scripts/deploy-aws-application.sh` (legacy MDM steps);
  - `install.sh` and `bootstrap-prod-mdm.sh` (legacy `mdm migrate`);
  - the rest of `scripts/ops`;
  - `examples/mdm_graph_dashboard`;
  - dbt `mdm_export` sources and gold `company`/`mdm_company`;
  - the infra Python scripts that import deleted modules (Mongo decision
    store, snowflake graph, filing text retention).
- **Local databases** are recreated without the legacy tables. A hosted
  database is dropped only on the operator's word.
