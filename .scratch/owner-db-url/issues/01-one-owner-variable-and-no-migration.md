# One owner variable, and nothing is called a migration

Status: open
Type: task

Operator: "you should not be using migration url it is confusing retire it asap", "use db_URL", "fold all duty names into the scheme ...
think kiss", "migration should not be used we are building a product". Phase 1 is the owner duty.

## Parts

- [x] One shared `owner_engine`/`owner_url` in `edgar_warehouse/database_connections.py`: `DB_URL` with the store's own database; a `DB_URL` that names a database keeps it (tests/unit/test_local_test_stores.py and the command tests)
- [x] `mdm init` replaces `mdm migrate`; every `migrate` subcommand is removed (rdm, rules, silver, bookkeeping, change-journal); the six `*_MIGRATION_DATABASE_URL` names and `STORE_`/`DESTINATION_MIGRATION_` are gone (a test fails on any return); `bookkeeping init` and `grant-profile` read `DB_URL`, not the runtime variable
- [x] The stores folder: `owner.env` (one `DB_URL`, no database) replaces `connection.env`; `governance.env` holds no owner login; local-test-stores, provisioning, reset, silver deploy, the qualification script and the catalog readers read it
- [x] Run live on the hosted instance: all six `init` commands under `owner.env`, each ok (2026-11-19 07:18 ET)
- [x] Skills, runbook and specs say `init` and `DB_URL`; CONNECTIONS.md holds the duty table (owner, runtime, governance, reader)
- [ ] CI green on every changed test (the storage-adapter, installed-bundle and integration tests need a server and ran only in CI)
- [ ] Phase 4: the word inside the code: internal `migrate` functions, the `existing_only` flag, the `migration` schema table and `migrations/` folders
- [x] Phase 2 in code: one `store_engine`/`store_url` (with optional `DB_PREFIX`); MDM, silver, RDM, the workers, context, rules, doctor, the Journal's and Bookkeeping's own defaults, `load_chain.py`, `readiness.py`, `profile_load`, `run_sample`, the exposure manifest read the loader file's `DB_URL`; the unit and architecture suites pass; the converted adapter and integration tests that run on a local server pass (2026-11-19 08:08 ET)
- [x] Phase 3 in code: `provision_hosted_store.py` provisions by duty file (loader, governance, reader; owner), making a missing file with a new password and refusing a file that names another login than its duty; local-test-stores makes one loader and one governance login; the monitor, the audit and `readiness.py` read `reader.env`'s `DB_URL`
- [x] `init` now refuses to recreate a Journal whose history table is missing (the guard `migrate` had), for PostgreSQL as the other engines already did
- [ ] CI green on the stacked branch (the installed-bundle and MySQL tests run only in CI); then rebase on main once the owner change merges
- [ ] Live: create the single `governance` login (approved) and fold the live `worker.env`, `governance.env` and `reader.env` to one `DB_URL` each, keeping the loader and reader passwords; then reset, init, readiness, load
- [ ] Catalog-reader logins (three, one per store, read by the catalog) keep their per-source names: a decision to confirm
- [x] Learning → skill: data-platform CONNECTIONS.md (the scheme), bookkeeping, change-journal, mdm-engineering and data-platform skills say `init`
