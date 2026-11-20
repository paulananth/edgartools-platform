# MDM, RDM and silver in one database, one mirror

Status: open
Type: task

Operator: "research if we can have one db and multiple schemas in postgress, where we can put togther mdm, rdm, silver in one db
and the rest in another db", then "Yes, open the ticket and start, make the skill intellgent".

## What the research found

- A managed mirror reads one Postgres database and may select tables from several of its schemas; each target schema keeps its
  source schema's name (mirror sub-skill; proved on a hosted test instance, `.scratch/single-iceberg-mirror/issues/01`).
- The instance allows two CDC publications (`snowflake_cdc.max_publications` 2, not settable through `POSTGRES_SETTINGS`), so
  three store databases cannot all be mirrored; one data database needs one publication.
- `SINGLE-DATABASE-ICEBERG.md` already names the target: `DB_EDGARTOOLS_MIRROR` with schemas `MDM`, `RDM`, `SILVER`, and lists
  the gates before production consolidation (callers, schema isolation, restricted roles, migrations, stored history, recovery,
  rollback). The three mirror databases made earlier went against it.
- The code supports one database for every store (`database_connections.store_url`: a `DB_URL` naming a database). Every store
  has its own schema except mastering, whose tables sit in `public`. Two groups of stores need a store-to-database map.

## Parts

- [x] Research: mirror scope, the publication limit, the earlier qualification, the code's store layout. 2026-11-19 21:19 ET
- [x] Skill: `CONNECTIONS.md` holds the two databases and two URLs and why; `HOSTED-MIRRORING.md` plans mirrors from the
      exposure list by database, checks the publication limit, and answers a shortage with the store layout. 2026-11-19 21:19 ET
- [ ] A mirror-plan script the skill runs (exposure list, layout, publication limit → the plan, or the refusal)
- [x] Consult the GoF reviewer: the shape stands; one finding, the store's database rule is copied in three places
      (`database_connections.store_url`, Bookkeeping's `default_url`, the Change Journal's `_default_url`), so the change goes in
      one resolver and the copies call it. 2026-11-19 21:19 ET
- [x] Operator: "mdm, rdm, silver is data_url, others are control_db, control_url do not have too many urls": two URLs a duty
      file, `DATA_URL` (the data database: mdm, rdm, silver) and `CONTROL_URL` (the control database: rules, bookkeeping,
      change_journal); no map. 2026-11-19 21:19 ET
- [x] One resolver: `store_url(store)` takes `DATA_URL` or `CONTROL_URL` by the store's group, with `configured`, `instance_url`
      and `url_variable`; Bookkeeping and the Change Journal, which ship alone, read `CONTROL_URL` themselves.
      `tests/unit/test_database_connections.py` failed first ("DB_URL is not set"), 11 pass. 2026-11-19 21:19 ET
- [x] Operator: "kiss 94 url will be nigthmree to maintain": one module names the URLs; everything else asks it.
      `tests/architecture/test_store_urls_have_one_owner.py` fails while any other file names one (79 left). 2026-11-19 21:19 ET
- [x] Every other `DB_URL` reader moves to the URL of its store's group; instance-wide scripts (monitor, hardening, reset, audit) to
      `DATA_URL`. `tests/architecture/test_store_urls_have_one_owner.py` passes: no file but the resolver names one. The scripts only
      their own tests used (`start-local-postgres.sh`, `provision-local-postgres-stores.sh`, `provision-clean-bookkeeping.py`, the old
      one-database-per-store layout) are deleted. 2026-11-19 22:14 ET
- [x] Operator: "yes" to rebuilding the shared local test server in the new layout when this merges (asked: "Do you approve
      rebuilding the shared local server at merge time?"). 2026-11-19 22:14 ET
- [x] The duty files written by provisioning and the local test server hold the two URLs: `provision_hosted_store.py` writes and
      checks `DATA_URL` and `CONTROL_URL` (one login, each naming its database; 14 tests); `local-test-stores.py` writes both, makes
      `data` and `control`, each store's schema under its own owner; `tests/integration/test_local_test_stores_postgres.py` 2 pass on
      real PostgreSQL 16 (init, a worker run, backup and exact restore with owners kept). 2026-11-19 22:14 ET
- [x] The Change Journal shares the control database: its PostgreSQL refusal of a database holding other tables is removed (it
      contradicted the operator's control database); the untracked-schema and checksum refusals stay. The bookkeeping and journal
      `init` default to the database their URL names. Test: `test_the_journal_shares_the_control_database_with_the_other_stores`. 2026-11-19 22:14 ET
- [x] Tests move to the two URLs; the shared `databases` fixture makes `control` and `data`. Single-store adapter tests pass on
      PostgreSQL and MySQL (8 files). 2026-11-19 22:14 ET
- [ ] ~~Mastering in schema `mdm` on PostgreSQL~~ not needed: MDM's owner owns the data database, so mastering and MDM's
      registration authority keep `public` (the mirror carries it as `PUBLIC`); rdm and silver keep their own schemas under their own
      owners. Moving mastering into `mdm` is its own change if the Gold names ask for it.
- [ ] Follow-up (no-DDL rule): the silver writer still stages each delivery in a temporary table, so the databases keep TEMPORARY
- [ ] Access by schema in a shared database: reset, hardening (the mirror login's CONNECT), readiness, catalog readers, local
      test stores
- [ ] `rules/exposure.yaml` and `rules/gold/gold.yaml`: one target database, mdm's source schema `mdm`
- [ ] Prove on the local test server with the two-database layout: init, a small load, links and master ids, the catalog reader
- [ ] Hosted: the operator's sign-off words, reset, init in the new layout, reload (hours; said before it starts)
- [ ] Hosted: the two mirrors dropped (approval) and one mirror of the data database created and read back
- [ ] Follow-up ticket: master ids and links as joins inside the data database
- [ ] Merge the PR when CI is green
- [ ] Learning → skill
