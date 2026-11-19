# Reinitialise the hosted stores with access guards

Status: open
Type: task

Operator: "stop all loaders, init and reinitalise using audit best practices". The load `fresh-v4` was at 31 of 43 steps when it
was stopped; the six databases (23 GB) were dropped and made again.

## Parts

- [x] Stop every loader: the scheduler and its step processes; the database showed 6 connections and no running work (2026-11-19 07:02 ET)
- [x] `infra/scripts/harden-hosted-roles.py`: connection limit, timeouts, loader `work_mem` ceiling and audit classes on four login roles; 16 guards applied, 0 refused; tests/unit/test_harden_hosted_roles.py: 5 passed (2026-11-19 07:02 ET)
- [x] Drop and make the six databases again, then init steps 3 to 8 of the runbook: six schemas, RDM codes (pins ok), registration, rules registered, silver tables, ten worker grants, `doctor` ok, catalog confirmed (2026-11-19 07:02 ET)
- [x] Learning → skill: `skills/data-operations/HOSTED-LOADS.md` (guards first, engine must match the code, `EDGAR_WAREHOUSE` is the executable, one scheduler per run label, stopping and resetting); runbook step 2b; aws-snowflake-operations and database-monitoring carry the access and memory lessons
- [ ] Start the load again (`load_chain.py --auto` from a fresh state file) and watch the memory and lock readings with the monitoring skill
- [ ] Retire the migration names: one `DB_URL` per duty file (owner, loader, governance, reader), `mdm init` for `mdm migrate`, no `*_MIGRATION_DATABASE_URL` (phase 1 started on its own branch; the loader, governance and reader names follow)
