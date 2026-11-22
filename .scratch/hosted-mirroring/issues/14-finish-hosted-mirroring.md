# 14: Finish hosted mirroring: the parts tickets 04 and 13 left open

Status: claimed
Type: task

The operator closed tickets 04 and 13 on 2026-11-21 ("close all ticket on this map"). Their parts that were not done moved here, unchanged in meaning.
Parts marked "approval" or "words" wait for the operator's own words before they run.

## Checklist

- [x] Access by schema in a shared database: covered, split by the operator ("1", 2026-11-22): reset, provisioning and the mirror login's CONNECT were done by the hosted reload in ticket 04 (2026-11-19 23:06 ET); hardening and catalog readers pass `tests/unit/test_harden_hosted_roles.py`, `test_catalog_readers.py`, `test_database_connections.py` and `tests/architecture/test_store_urls_have_one_owner.py` (36 pass); `local-test-server` holds the `data` database with schemas `mdm`, `public`, `rdm`, `silver` 2026-11-22 15:47 ET. The live `discovery_reader` limit is held (Readiness line); the gate pass stays open; the 30 tables left in `public` are not yet explained (see the hosted reset line)
- [x] `destination/authorised_data_sharing.yaml` and `destination/gold/gold.yaml` (moved from `rules/`, tickets 12 and 15): already one target database (`mirror.database` in `rules/snowflake.yaml`, read by both) and mdm's source schema `mdm` on `DATA_URL` (layers `mdm`, `rdm`, `silver`, all one source database); read from the files, and `test_gold_views.py` pins the database and the mirror schemas 2026-11-22 16:11 ET
- [ ] Prove on the local test server with the two-database layout: init, a small load, links and master ids, the catalog reader
- [x] Readiness, the connection limit: `discovery_reader` holds connection limit 10 on the hosted store (read from `pg_roles`: discovery_reader 10, edgar_loader 300, governance 10, ops_reader 10) and `harden-hosted-roles.py` reports "every login role holds its guards" 2026-11-22 16:22 ET. The gate does not pass yet: CODE (CI not green on this checkout), ENGINE (not built here), AUDIT (only `SCH.postgres` fails, see the hosted reset line) and CATALOG (partial) fail; the other ten checks pass
- [ ] Readiness gate: a full pass of `readiness.py` (waits for the hosted reset into `mdm`, the engine build, the catalog match and green CI on the commit)
- [x] Mastering moved from `public` into schema `mdm`, with audit objective SCH: PR #1997 2026-11-21 09:27 ET
- [ ] Hosted: the live stores hold the mastering tables in `public` until the next init; a reset (init steps 1-9) creates them in `mdm`, the audit's SCH control passes, and the one mirror is created with `MDM` as the schema
- [ ] Follow-up (no-DDL rule): the silver writer still stages each delivery in a temporary table, so the databases keep TEMPORARY
- [ ] Finish under five minutes on this store: rebase `claude/links-reads-one-pass`, merge, rerun `--finish`
- [ ] The snapshot cost of the one mirror read from metering history against the bounds (5 credits for a mirror)
- [ ] Hosted: rename the two kept databases (drop the `DB_` prefix) and drop the two old targets (waits for the operator's ANANP11 words); a one-line change per name in `rules/snowflake.yaml`
- [x] The orphan targets `DB_EDGARTOOLS_MIRROR_MDM` and `DB_EDGARTOOLS_MIRROR_SILVER`: dropped (operator, 2026-11-22: "dropped targets ... check and update"); verified `SHOW DATABASES LIKE '%EDGARTOOLS%'` as the auditor role lists only `EDGARTOOLS_GOLD` and `EDGARTOOLS_GOVERNANCE` 2026-11-22 12:08 ET (the auditor sees only databases its role can see)
- [x] Owner role and Gold database ownership in the access Terraform root: declared from `rules/snowflake.yaml` (`terraform validate` passes; two tests, the first failed on the missing resource); the owner role's grant to ACCOUNTADMIN is not planned there (the skill never plans against the administrator): it stays the administrator's SQL from `database_owner_sql.py`. Import of the role and the ownership comes with the next access apply (the governance database is gone, so one ownership remains) 2026-11-22 16:23 ET
- [x] Hosted RDM's six old code-set versions: already removed by ticket 08 (`rdm prune`, `rdm retire`, 2026-11-20: 17 versions and 7,408 codes became 11 and 7,272); the gate's REFERENCE check reads 7,272 codes today 2026-11-22 16:22 ET
- [x] Follow-up ticket: master ids and links as joins inside the data database: opened as ticket 16 (`16-master-ids-and-links-as-joins-in-the-data-database`) 2026-11-22 16:22 ET
- [x] Credential policies: created both in `EDGARTOOLS_GOLD.POLICIES` from `rules/snowflake_policy.yaml`, attached (password policy to the account, keypair-only to the 4 service users; live `POLICY_REFERENCES` read), `EDGARTOOLS_GOVERNANCE` dropped as the administrator on the operator's words 2026-11-22 ("use ananp11 to drop the governance", option "move, then drop") 2026-11-22 12:12 ET. Done by SQL, not the access Terraform root (no access-admin identity yet): the next access apply imports the schema, two policies and attachments first
- [x] Re-run the audit on `snowflake`: POL PASS, live read through the policy reader procedure (ticket access-audit 02) 2026-11-22 12:34 ET
- [ ] Learning → skill: name the skill line this ticket changed, or "none"
