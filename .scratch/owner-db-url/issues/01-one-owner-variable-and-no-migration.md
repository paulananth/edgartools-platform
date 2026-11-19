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
- [x] CI green on every changed test: PR 1915 merged with all 12 checks green. 2026-11-19 15:00 ET
- [ ] Phase 4: the word inside the code: internal `migrate` functions, the `existing_only` flag, the `migration` schema table and `migrations/` folders
- [x] Phase 2 in code: one `store_engine`/`store_url` (with optional `DB_PREFIX`); MDM, silver, RDM, the workers, context, rules, doctor, the Journal's and Bookkeeping's own defaults, `load_chain.py`, `readiness.py`, `profile_load`, `run_sample`, the exposure manifest read the loader file's `DB_URL`; the unit and architecture suites pass; the converted adapter and integration tests that run on a local server pass (2026-11-19 08:08 ET)
- [x] Phase 3 in code: `provision_hosted_store.py` provisions by duty file (loader, governance, reader; owner), making a missing file with a new password and refusing a file that names another login than its duty; local-test-stores makes one loader and one governance login; the monitor, the audit and `readiness.py` read `reader.env`'s `DB_URL`
- [x] `init` now refuses to recreate a Journal whose history table is missing (the guard `migrate` had), for PostgreSQL as the other engines already did
- [x] CI green on the stacked branch and rebased on main: PR 1916 merged with all 12 checks green after two fixes (the doctor test's fixture and its store assertion). 2026-11-19 15:00 ET
- [x] Live: the single `governance` login was created (member of `mdm_governance` and `rules_governance`, now NOLOGIN groups) and the live `worker.env`, `governance.env` and `reader.env` hold one `DB_URL` each, loader and reader passwords kept; every duty login connects to its databases (the readiness `LOGINS` check). 2026-11-19 15:00 ET
- [x] Catalog-reader logins folded to one. Operator, 2026-11-19 15:00 ET: "Catalog readers: whether to keep three logins or fold them. To 1". One login `discovery_reader` holds CONNECT on `mdm`, `rdm` and `silver` and SELECT on exactly the exposure list's tables in each; the three per-store logins (`discovery_reader_mdm`, `_rdm`, `_silver`) were revoked and dropped, the old file kept as `reader.env.three-logins`. `tests/unit/test_catalog_readers.py` (the shared-login test failed without the password reuse).
- [x] Learning → skill: data-platform CONNECTIONS.md (the scheme), bookkeeping, change-journal, mdm-engineering and data-platform skills say `init`
