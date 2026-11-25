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
  monitor reads each store database from the map (tests/unit/test_load_jobs.py, tests/unit/test_readiness.py) (2026-11-25 10:59 ET)
- [x] Resets never name the config database (tests/unit/test_reset_hosted_databases.py; `reset-hosted-tables.py --store` choices) (2026-11-25 10:59 ET)
- [x] Skills and docs say three databases (CONNECTIONS, HOSTED-LOADS, HOSTED-MIRRORING, the init runbook, the
  operations, onboarding, monitoring and journal skills) (2026-11-25 10:59 ET)
- [ ] Integration and storage-adapter tests that reach Rules use `CONFIG_URL` and pass locally on PostgreSQL
- [ ] Review: Standards, Spec and GoF
- [ ] PR open, CI green, merged
- [ ] Hosted: provision the config database and add `CONFIG_URL` to the duty files (`provision_hosted_store.py --confirm`;
  needs the operator's word: it changes the live instance)
- [ ] Hosted: copy the `rules` schema from control to config (`pg_dump --schema=rules` from control, restore into config
  as the owner), check each table's row count is equal, then drop `rules` from control; needs the operator's word
- [ ] Shared local server: the same copy, once no agent on older code still reads Rules from control
- [ ] Hosted clear-out of data and control follows on `.scratch/hosted-reset/` with config kept
- [ ] Learning → skill: data-platform CONNECTIONS.md "Six stores live in three databases" and data-operations
  HOSTED-LOADS.md "Rules configuration is never reset"
