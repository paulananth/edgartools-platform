# Hosted foundation test approval plan

Status: not run; approval required.

## Exact isolated resources

Snowflake connection: `edgartools-prod`; role: `ACCOUNTADMIN`; same AWS Ohio account/region as the reviewed instance.

- New Snowflake Postgres instance: `EDGARTOOLS_MIRROR_QUAL_43FC42B3`.
- Source database: `postgres` on that new test instance only.
- Source format: PostgreSQL 16, STANDARD_M, 10 GB, HA off.
- Network: reuse `EDGARTOOLS_PROD_MDM_POSTGRES_POLICY` unchanged; no new allowlist entries and no production-instance changes.
- Mirror: `mirror_qual_43fc42b3`.
- New Snowflake target: `DB_EDGARTOOLS_MIRROR_Q_43FC42B3`.
- Optional owned consumer test role: `MIRROR_QUAL_READER_43FC42B3`.
- Production name `DB_EDGARTOOLS_MIRROR` is reserved and will not be created.

## What runs

Use existing installed instance/connection helpers and SQL clients; no new helper script. One source database holds the documented three schemas, three final tables and six exclusion controls. Seed nine invented rows. Review the exact synthetic table list as part of the test requirements/mapping plan. This is a manually reviewed Iceberg capability experiment, not proof of the missing automatic tag selector.

After read-only pre-flight succeeds, use one CREATE_MIRROR call with the three explicit final tables, postgres_schemas NULL, target_table_type ICEBERG, refresh interval 10 minutes, warehouse NULL and external_volume NULL. Grant the mirror application only the required access to this new test instance. Provisioning saves credentials privately; never print raw create/describe access-role responses.

Verify target membership, actual Iceberg metadata and every expected key/decimal. Then run the documented committed insert/update/delete and rollback; verify exact final sets and stable repeated reads. Where the scoped consumer role is created, require reads to succeed and writes to fail. Do not migrate, process or sample production data, provision a Gold database or invoke external inference.

## Bounds and cost

One temporary STANDARD_M instance, one small mirror, one serverless apply task and their storage are billable. No new virtual warehouse is requested. Check at 30-minute observation points, with a 90-minute execution deadline after fixture readiness. Provisioning time and partial-failure cleanup must also be recorded. Use the current account pricing before create; no fixed dollar cap is claimed without verifying compute, storage and apply-task rates.

## Cleanup included in the requested approval

After evidence is captured, remove only this named mirror and target database with an explicit drop_target_database setting, the optional owned reader role, and this named test Postgres instance. Do not remove or alter the reused network policy, other instances, databases, roles or local shared volumes. On a failed qualification, still perform that same authorized scoped cleanup; report any resource whose removal could not be verified. No silent restart or repeated snapshot to hide a failed result.

## Separate gates

Gold/dbt, actual configuration-driven tag selection, OpenMetadata/AutoOntology enforcement and production consolidation remain blocked/not run until independently qualified. Success here proves one source database with three schemas can feed one actual Iceberg mirror database, not the complete platform conversion.
