# Drop and reinitialize the hosted stores

Status: claimed
Type: task

## Operator rulings

- "decommission the old postgress snoflake instance"; asked how, the operator chose "Drop it permanently now"
  (2026-11-17 20:53 ET). EDGARTOOLS_PROD_MDM was dropped with no backup.
- The question named it "the hosted production MDM store". It held all six stores' databases (`mdm`, `rdm`, `rules`,
  `bookkeeping`, `change_journal`, `silver`); the question did not say so. Their contents are gone.
- "re init using skills snowflake hosted postgress mdm, rdm , silver, bookkeeping, change journal database", then
  "fix skills", "and runbook", "data platform skills".

## Parts

- [x] Drop EDGARTOOLS_PROD_MDM (2026-11-17 20:53 ET; live: "successfully dropped", only the Iceberg test instance left)
- [x] Recreate EDGARTOOLS_PROD_MDM: STANDARD_M, 50 GB, PostgreSQL 16, the existing network policy; administrator saved privately (2026-11-17 21:01 ET; pg_connect --create)
- [x] Skill gap fixed: no command gave a fresh instance its logins and databases. `skills/data-platform/scripts/provision_hosted_store.py` does it from the hosted folder's own files, no login rotated (2026-11-17 21:01 ET; tests/unit/test_provision_hosted_store.py, 3 passed)
- [x] Runbook step 2 and the operations skill name the command; the operations skill says one instance holds all six stores, that a drop deletes them all, and how a network policy admits an instance (2026-11-17 21:01 ET)
- [ ] ~~The connections guide names the command~~ deferred to .scratch/hosted-store-reinit/issues/02-connections-guide-names-provisioning.md: the open codex/hosted-catalog-sync work changes the same file
- [x] Instance READY and its hostname resolving: READY within minutes; this machine had cached "not found" while a public resolver answered; the operator flushed the cache (2026-11-17 21:14 ET)
- [x] Logins and six databases created; the hosted folder's URLs moved to the new instance: 8 logins, 1 group, 6 databases, 32 URLs moved. The first dry run listed `rules_agent` as a group to create though it is a login; fixed; `test_a_group_that_is_also_a_login_is_made_once_as_the_login` failed before the fix on `assert "create group rules_agent" not in steps` (2026-11-17 21:14 ET; live run; tests/unit/test_provision_hosted_store.py, 4 passed)
- [x] Runbook steps 3 to 7: 6 schemas with their checksums; 15 RDM pins ok, approved in the operator's words above; registration login granted; rules check ok, 19 digests registered, silver tables created; 10 of 10 worker profiles granted; `doctor` ok under worker.env (2026-11-17 21:14 ET; live run). The stores hold no data: it was lost with the drop
- [x] Review fixes (2026-11-17 21:19 ET; tests/unit/test_provision_hosted_store.py, 8 passed; each new test failed on the old script):
  - a URL the parser refuses printed its whole address, password included; now only the error's class
    (`test_a_url_the_parser_refuses_prints_its_class_never_its_password` failed on `assert ("netloc '..." == 'failed: ValueError'`);
  - a store no URL gives a login is refused (`test_a_store_no_login_connects_to_is_refused`: DID NOT RAISE);
  - a group member no URL names is refused before anything is made (`test_a_group_member_no_url_names_is_refused_before_anything_is_made`: DID NOT RAISE);
  - a database another role owns is refused, never adopted (`test_a_database_another_role_owns_is_never_adopted`: DID NOT RAISE).
  Not changed: separate owner roles. On a hosted instance the administrator is the owner login
  (`MDM_MIGRATION_DATABASE_URL`, as `reset-hosted-databases.py` and RUNBOOK step 2 say); local servers make owner roles.
- [x] Learning → skill: aws-snowflake-operations "The hosted MDM store" (one instance holds six stores; a new hostname; network rules) and data-operations RUNBOOK steps 1 and 2 (a fresh instance's command, the cached lookup, today's `edgar-warehouse`, the comment's characters) (2026-11-17 21:14 ET)
