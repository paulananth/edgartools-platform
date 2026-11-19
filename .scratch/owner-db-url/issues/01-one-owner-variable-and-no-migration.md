# One owner variable, and nothing is called a migration

Status: open
Type: task

Operator: "you should not be using migration url it is confusing retire it asap", "use db_URL", "fold all duty names into the scheme ...
think kiss", "migration should not be used we are building a product". Phase 1 is the owner duty.

## Parts

- [x] One shared `owner_engine`/`owner_url` in `edgar_warehouse/database_connections.py`: `DB_URL` with the store's own database; a `DB_URL` that names a database keeps it (tests/unit/test_local_test_stores.py and the command tests)
- [x] `mdm init` replaces `mdm migrate`; every `migrate` subcommand is removed (rdm, rules, silver, bookkeeping, change-journal); the six `*_MIGRATION_DATABASE_URL` names and `STORE_`/`DESTINATION_MIGRATION_` are gone (a test fails on any return); `bookkeeping init` and `grant-profile` read `DB_URL`, not the runtime variable
- [x] The stores folder: `owner.env` (one `DB_URL`, no database) replaces `connection.env`; `governance.env` holds no owner login; local-test-stores, provisioning, reset, silver deploy, the qualification script and the catalog readers read it
- [x] Run live on the hosted instance: all six `init` commands under `owner.env`, each ok ({{now}})
- [x] Skills, runbook and specs say `init` and `DB_URL`; CONNECTIONS.md holds the duty table (owner, runtime, governance, reader)
- [ ] CI green on every changed test (the storage-adapter, installed-bundle and integration tests need a server and ran only in CI)
- [ ] Phase 2: the six runtime `*_DATABASE_URL` names become one `DB_URL` in `worker.env` (the loader), read per store by the same function
- [ ] Phase 3: governance (`MDM_REGISTRATION_`, `RULES_MDM_ACTIVATION_`, the rules login) and reader (`DIAGNOSE_`, `PROFILE_`) become `DB_URL` in their files; `CHANGE_LEDGER_DATABASE_URL` traced
- [ ] Phase 4: the word inside the code: internal `migrate` functions, the `existing_only` flag, the `migration` schema table and `migrations/` folders
- [ ] `init` has no history guard of its own: the Journal's refusal to recreate missing event storage was a property of `migrate`; decide whether `init` refuses when the schema is tracked but a table is missing
- [x] Learning → skill: data-platform CONNECTIONS.md (the scheme), bookkeeping, change-journal, mdm-engineering and data-platform skills say `init`
