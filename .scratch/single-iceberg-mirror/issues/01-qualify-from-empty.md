# Qualify one Iceberg mirror database from an empty test source

Status: resolved
Type: task

## Parts

- [x] Verify current managed-mirror database and Iceberg constraints against official create/procedure references, 2026-11-15 12:54 ET.
- [x] Update platform and installed mirror skills with isolated qualification, Iceberg format and explicit expected results, 2026-11-15 12:54 ET.
- [x] Reuse Docker/psql/Snow CLI and existing clients; no demonstrated orchestration gap and no new helper script, 2026-11-15 12:54 ET.
- [x] Validate 122 policy/genericity/path/installed-portability checks and Standards/Spec/GoF reviews; installed mirror validation passed, 2026-11-15 12:54 ET.
- [x] Publish the skill update in draft PR #1805; local checks and fixture execution verified on the skill changes, CI remains pending, 2026-11-15 12:56 ET.
- [x] Run the hosted synthetic qualification after a concrete test-resource plan and explicit billable-operation approval: capability proof only; every stage that ran passed, and four are deferred below (2026-11-17 21:23 ET)
  - [x] Approval recorded: the operator answered "Approve the run as planned (Recommended)" at 2026-11-17 20:39 ET to the plan in HOSTED-TEST-PLAN.md: a temporary STANDARD_M instance, one Iceberg mirror, 9 invented rows, a 90-minute deadline and scoped cleanup of only the named resources (2026-11-17 20:47 ET)
  - [x] Read-only pre-flight: role ACCOUNTADMIN in AWS us-east-2; the only instance is production MDM (untouched); no `DB_EDGARTOOLS_MIRROR%` database; the reused policy exists; ACCOUNTADMIN holds the mirror admin role; CREATE_MIRROR takes TARGET_TABLE_TYPE and EXTERNAL_VOLUME (2026-11-17 20:47 ET; live Snowflake reads)
  - [x] Network finding: the installed checker reported the reused policy NOT_ALLOWED, because it read only ALLOWED_IP_LIST and ignored the policy's network rules. The policy's one rule is POSTGRES_INGRESS open to all addresses, as its committed template intends. The operator ruled "fix the network policy and update the skill to get it right": the policy needed no change; the installed checker (outside this repository) now resolves POSTGRES_INGRESS rules and reports ALLOWED (2026-11-17 20:47 ET; 3 checker tests, the all-addresses case failing on the old checker; live recheck ALLOWED)
  - [x] Cost checked: Postgres compute is 3.00 USD a credit on the account rate sheet; the same family measured 0.035 credits an hour over 48 hours (2026-11-17 20:47 ET)
  - [x] Cleanup SQL written and a deadline guard started before create: the guard would have dropped only the named resources at 23:02 ET; it exited unused once the run finished. The execution deadline was 22:41 ET, 90 minutes from the mirror's creation, not from fixture readiness as the plan says (that would have been 22:21 ET); the guard ran 21 minutes later as a backstop. The run ended at 21:22 ET, inside both (2026-11-17 21:23 ET)
  - [x] Test instance created and READY; fixture seeded and read back (9 rows, exact text) (2026-11-17 20:51 ET READY; live read)
  - [x] Selection proved: exactly the three final tables; six exclusion controls absent (read 21:16 ET: `LIST_MIRRORED_TABLES` 3 rows, all `final_data`; `SHOW ICEBERG TABLES` places them in the three schemas `MDM`, `RDM` and `SILVER`; `SHOW ICEBERG TABLES` no internal or untagged table) (2026-11-17 21:23 ET)
  - [x] Mirror created (ICEBERG, serverless, 10 minutes); three tables REPLICATING; each target an actual Iceberg table: created 21:11 ET, all three REPLICATING by 21:16 ET; each base table on the Snowflake catalog and managed volume, with a `$CHANGES` companion and one `SNOWFLAKE_CDC_LOGS` table; types `NUMBER(19,0)` and `NUMBER(38,9)` (2026-11-17 21:23 ET)
  - [x] Initial snapshot: every key and decimal equal as text: 3 rows in each layer, keys 1, 2 and 9007199254740993, the 38-digit decimal exact (read 21:17 ET, before the changes; recorded 2026-11-17 21:23 ET; one-statement read)
  - [x] Committed cross-schema change and rolled-back change: final keys 2, 4 and 9007199254740993 with exact measures; key 1 and key 99 absent; one-statement read; repeated read stable: changes committed 21:17:53 ET, applied in the mirror by 21:21:08 ET, the second read 30 seconds later identical in all three layers (2026-11-17 21:23 ET)
  - [x] Read-only consumer role: SELECT succeeds, INSERT denied: 9 rows read; the INSERT refused for lack of the INSERT privilege. Not tried: an UPDATE, and a read of a `$CHANGES` companion, which the role was never granted (2026-11-17 21:23 ET)
  - [x] Cleanup: mirror and target dropped (drop_target_database TRUE), reader role and test instance dropped; only production MDM remains: no mirror database, no reader role, no mirror integration left. The skill's named form `drop_target_database => TRUE` was refused ("illegal mixing of named and positional arguments"); the positional form dropped it (2026-11-17 21:23 ET; live check)
  - [ ] ~~Every plan bound recorded~~ deferred to .scratch/single-iceberg-mirror/issues/02-select-by-tags-and-build-gold.md: no 30-minute checkpoint fell due (the mirror took 11 minutes), the create start was not kept (READY 20:51 ET), and only Postgres compute was priced, not the serverless apply or Iceberg storage. The mirror application held only USAGE on the test instance
  - [x] Evidence recorded per stage, labelled capability proof only (2026-11-17 21:23 ET; this list)
  - [ ] ~~Tables selected by approved mappings and tags~~ deferred to .scratch/single-iceberg-mirror/issues/02-select-by-tags-and-build-gold.md: this run named its three tables
  - [ ] ~~OpenMetadata and AutoOntology see the same table set~~ deferred to .scratch/single-iceberg-mirror/issues/02-select-by-tags-and-build-gold.md: needs the tag selection first
  - [ ] ~~A Gold model reads the mirror~~ deferred to .scratch/single-iceberg-mirror/issues/02-select-by-tags-and-build-gold.md: a separately approved Gold target
- [x] Learning → skill: SINGLE-DATABASE-ICEBERG.md separates documentation, executed local fixture, hosted Iceberg, tag enforcement and production consolidation, no new helper needed (2026-11-15 12:54 ET); after the hosted run its sections 4 and 6 name the companion tables, the listing's columns, the target types, decimals read as text in Snowflake and table-by-table consumer grants, and its cleanup passes `DROP_MIRROR`'s target flag positionally (2026-11-17 21:23 ET). The installed snowflake-postgres skill, which lives outside this repository, got the same drop example and the network checker fix; this repository holds no copy of either

## Scope

The requested consumer target is one mirror database containing Iceberg tables
from final master, reference and silver outputs, selected by approved mappings
and tags. The current three source databases are not consolidated by this task.
Only the test resources in the approved plan were created and removed; no source
migration was approved. The existing production target name is reserved for a later
approved production deployment, not consumed by a qualification run.

## Local execution evidence

The documented seed, committed cross-schema mutations and rollback SQL blocks
ran on disposable PostgreSQL 16 with no network access or shared volume. One
database held three schemas, three selected tables and six exclusion controls.
All nine initial rows and all nine final rows matched exact independent
expectations, including the integer above binary floating-point precision and
the wide decimal. Every selected table was logged and had a primary key.
Rollback left the final set unchanged. Elapsed time: 3.23 seconds; the container
was removed. This is fixture proof, not a Snowflake or automated-tag proof.

121 skill-policy/genericity/path checks and isolated skill-bundle portability
passed. Installed mirror skill validation passed. The hosted Iceberg run and
consumer access then ran (Parts); tag resolution/publication, dbt and production
consolidation remain not run or blocked at their explicit gates.

## Approval artifact

[HOSTED-TEST-PLAN.md](../HOSTED-TEST-PLAN.md) names a new disposable hosted
instance, one Iceberg target, the exact fixture scope, a 90-minute deadline,
cost boundaries and scoped cleanup. It ran as approved; the Parts hold each stage's result. Existing production
stores and the reserved production target remain untouched.
