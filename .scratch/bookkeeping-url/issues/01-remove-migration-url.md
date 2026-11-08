# Remove BOOKKEEPING_MIGRATION_DATABASE_URL

Type: task
Status: claimed (Grok)

## Question

Bookkeeping init, migrate and grant-profile used a second env var,
`BOOKKEEPING_MIGRATION_DATABASE_URL`, for the owner login. MDM already uses
one key (`MDM_DATABASE_URL`) set to the owner for migrate and to the runtime
login for work. Use that same pattern for Bookkeeping.

## Parts

- [x] CLI `init`, `migrate` and `grant-profile` read `BOOKKEEPING_DATABASE_URL` (unit tests `test_bookkeeping_cli_does_not_name_a_migration_url`, `test_local_test_stores.py`; 2026-11-08 16:17 ET)
- [x] `connection.env` sets that key to the owner; `worker.env` keeps the runtime login and unsets the retired name (`test_bookkeeping_owner_uses_the_runtime_url_key`; 2026-11-08 16:17 ET)
- [x] Tests, skills, SPEC and install copy name only `BOOKKEEPING_DATABASE_URL` (skill text + install.sh; 2026-11-08 16:17 ET)
- [x] Drop unused `BOOKKEEPING_VALIDATION_DATABASE_URL` (never read by code) (`skills/change-journal/SPEC.md`; 2026-11-08 16:17 ET)
- [x] Retire `BOOKKEEPING_ADMIN_DATABASE_URL`; provision opens `postgres` from `BOOKKEEPING_DATABASE_URL` (`test_provision_script_uses_the_bookkeeping_url_key`; 2026-11-08 16:17 ET)
- [x] Document `BOOKKEEPING_MANIFEST_ROOT` in bookkeeping RUN, SPEC and local-agent-testing (2026-11-08 16:17 ET)
- [x] RUN.md names which env file holds `BOOKKEEPING_DATABASE_URL` (`worker.env` / `verifier.env` / `connection.env`; 2026-11-08 16:42 ET)
- [x] Drop the copied seven-wastes line and the SKILL Run `BOOKKEEPING_MANIFEST_ROOT` sentence (KISS; 2026-11-08 16:38 ET)
- [x] Learning → skill: bookkeeping RUN.md Configuration and SPEC Local use — one store URL key; `BOOKKEEPING_MANIFEST_ROOT` is the frozen-rules folder in `worker.env`. SKILL.md has no seven-wastes copy. PR unpublished: overlap_guard STOP vs Codex (2026-11-08 16:38 ET)
- [x] Publish PR https://github.com/paulananth/edgartools-platform/pull/1504 head `cc453c03` (operator asked push despite overlap_guard STOP on closed Codex worktrees; 2026-11-08 16:45 ET)
