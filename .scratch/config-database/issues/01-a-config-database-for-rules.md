# 01: A config database for Rules, apart from data and control

Status: open
Type: task
Owner: claude (branch `claude/config-database`)

## Operator rulings

- "first investigate we need a config db for rules and other configuration items so that that can be excluded from
  destruction" (2026-11-25)
- "control should only have control no cnfiguration" (2026-11-25)
- "we have to databases data and control, we need another database for configuration, this does not need to be in
  postgress but postgress is ok too, need options kiss no 7 wastes" (2026-11-25)
- Of four options (a third Postgres database, Git files, S3 objects, a Snowflake table), the operator chose a third
  Postgres database on the same instance: "A, CONFIG_URL is fine, go ahead" (2026-11-25).
- Live moves: "yes do both, keep rdm in the mirror" (2026-11-25 11:58 ET): provision and copy on the hosted instance and
  on the shared local server; the mirror keeps `rdm.published_code` (Gold's code-set dimensions and hierarchies read it).

## What it is

Three databases on the one instance, each store a schema: `data` (mdm, rdm, silver), `control` (bookkeeping,
change_journal) and `config` (rules: `policy`, `dataset_reading`, `rules_used`, `draft`). A duty file holds one URL a
database: `DATA_URL`, `CONTROL_URL`, `CONFIG_URL`. No reset names `config`: `reset-hosted-databases.py` drops data and
control only, and `reset-hosted-tables.py` offers no `rules` store. `mdm.migration` and `silver.table_spec` stay in the
data database: Silver registration writes `table_spec` with the table's DDL, and the table reset already refuses both.

## Checklist

- [x] Store map: `rules` is the config database's, `url_variable` gives `<DATABASE>_URL` from the map, so a store reaches
  its database in one place (tests/unit/test_database_connections.py) (2026-11-25 10:59 ET)
- [x] Hosted provisioning makes the config database with CONNECT for every duty login, and gives an existing duty file
  the URL of a database it lacks, for its own login, keeping its other lines (tests/unit/test_provision_hosted_store.py,
  `test_a_duty_file_missing_a_database_is_given_it_for_its_own_login_and_keeps_its_other_settings`) (2026-11-25 10:59 ET)
- [x] Local stores make the config database and write `CONFIG_URL` into every duty file (tests/unit/test_local_test_stores.py) (2026-11-25 10:59 ET)
- [x] Readiness checks every duty login against every store database and reads the Rules counts from config; the load
  monitor reads each store database from the map (tests/unit/test_load_jobs.py and tests/unit/test_readiness.py pass;
  no unit test reads the config database there: the hosted readiness run below proves it) (2026-11-25 10:59 ET)
- [x] Resets never name the config database (tests/unit/test_reset_hosted_databases.py; `reset-hosted-tables.py --store` choices) (2026-11-25 10:59 ET)
- [x] Skills and docs say three databases (CONNECTIONS, HOSTED-LOADS, HOSTED-MIRRORING, the init runbook, the
  operations, onboarding, monitoring and journal skills) (2026-11-25 10:59 ET)
- [x] Integration and storage-adapter tests that reach Rules use `CONFIG_URL` and pass locally: 60 integration tests,
  47 storage-adapter and engine tests on PostgreSQL, 5 storage-adapter tests on MySQL (2026-11-25 11:05 ET)
- [x] Review (reviewer agent, three axes): GoF no findings; Standards and Spec fixed: provisioning checks every file
  before changing any and adds an `unset` line where none is, readiness LOGINS connects with each URL the duty file names
  so a file without `CONFIG_URL` keeps the gate shut (`test_a_duty_login_is_tried_on_each_database_by_its_own_url_and_a_missing_url_keeps_the_gate_shut`
  fails on the earlier check: it read `answers`), STORES.md and native-gleif name the config database. Kept: the MDM
  init file's own comment (its text is the installed checksum), tests that make the Rules schema in their one test
  database (2026-11-25 11:05 ET)
- [x] PR ready, CI green and merged: #2135, `merge_on_green.sh` merged head `7abcdb38` (2026-11-25 12:12 ET)
- [x] Hosted: config database made, CONNECT for the loader, governance and reader logins, `CONFIG_URL` added to the four
  duty files with their own logins (copies kept as `*.env.before-config`); no client session and no load was running
  (`db_monitor.py sessions` 0, the load worker idle) (2026-11-25 12:03 ET)
- [x] Hosted: `rules init` on config, then every row copied from control as the owner: `rules_used` 21, `policy` 2,
  `dataset_reading` 21, `draft` 0, each table's rows equal by digest; the loader reads 2 policies and 21 readings from
  config and `doctor` answers for every store (2026-11-25 12:03 ET)
- [x] Hosted: the `rules` tables and schema dropped from control after the merge, each table's rows first checked equal
  in config (`rules_used` 21, `policy` 2, `dataset_reading` 21, `draft` 0) and no other client session on control (2026-11-25 12:12 ET)
- [x] Shared local server (stopped, started for this and stopped again): config database made, `rules init` on it,
  `CONFIG_URL` in every duty file; its control `rules` held only an empty `rules_used`, so nothing was copied (2026-11-25 12:03 ET)
- [x] Shared local server: the empty `rules.rules_used` and the `rules` schema dropped from control after the merge;
  the server started for it, its env files rewritten for the new port, and stopped again (2026-11-25 12:12 ET)
- [ ] Shared local server: its MDM schema stamp differs from today's `mdm init` ("Installed migration checksum differs")
  and its registry is an older layout (`mdm.policy` in data): it needs its own reset before a load; found here, not changed
- [ ] Hosted: provisioning's last check refused the loader, which can create in the data database's `lake_struct` schema
  (Snowflake's `pg_lake` schema); found here, not changed: the grant needs its own decision
- [ ] Hosted readiness passes with the config database (LOGINS and REGISTERED read it)
- [ ] Hosted clear-out of data and control follows on `.scratch/hosted-reset/` with config kept
- [x] Learning → skill: data-platform CONNECTIONS.md "Six stores live in three databases" and data-operations
  HOSTED-LOADS.md "Rules configuration is never reset" (2026-11-25 12:12 ET)
