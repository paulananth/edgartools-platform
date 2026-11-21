# The create plan for the three mirrors, after the first load

Status: resolved
Type: task

The operator said "Approved" (2026-11-19 12:37 ET) to the question "approval to create the mirror after the load finishes". Recorded as given. In plain
words it approves creating the mirrors of the exposed tables once the first load has finished. It is not the approval the guide requires
before each `SNOWFLAKE.POSTGRES.CREATE_MIRROR` (HOSTED-MIRRORING.md: each plan names its source database, tables, target database, refresh
interval, serverless or warehouse choice, exclusions, insert-only tables and cost, and is approved before it runs). It changes nothing.
No credential, connection or Snowflake object was given or created.

## Parts

- [x] Record the operator's word and what it covers. 2026-11-19 12:37 ET
- [x] Draft the plan below from `rules/exposure.yaml` (19 tables, three stores) and the guide's one-mirror-per-source-database rule. 2026-11-19 12:37 ET
- [x] Read-only connection and pre-flight facts. Operator, 2026-11-19 14:07 ET: "You may use ANANP11 once" (answering which admin to use for the read-only bootstrap; the rule against ANANP11 stands otherwise and the permission is spent). In that one session: grants to the existing audit role `EDGARTOOLS_PROD_AUDITOR` (USAGE on `DB_EDGARTOOLS_GOLD` and its schemas, REFERENCES on its tables: metadata, no rows; also in Terraform, validated), and one read of the instance: `EDGARTOOLS_PROD_MDM`, `STANDARD_M`, 75 GB, PostgreSQL 16, READY, no HA, not burstable, so the pre-flight's family check passes. No new user or key; no secret printed.
- [x] Credit rates. Operator, 2026-11-19 14:14 ET: "Use admin the provide the required permission" (ANANP11 used again on those explicit words; the memory note records each use). One grant: the `ORGANIZATION_BILLING_VIEWER` database role to the audit role (read-only, shows the rate sheet and also invoices; in Terraform, validated). Read as the audit role from `RATE_SHEET_DAILY` (latest day): Postgres compute 3.00 USD per credit, Postgres storage 117.76 USD (the sheet's storage unit), serverless tasks 3.00, warehouse compute 3.00, cloud services 3.00, query acceleration 3.00. The sheet lists only service types the account has used, so a mirror's own service types (the serverless apply, Iceberg storage) are not in it yet: the plan states them as assumed at the compute rate and confirms them after the first day.
- [x] The mirror's grant sequence, and two permissions it does not name. Operator: "Yes" (ANANP11 once, for the mirror operator): role and key-pair service user `EDGARTOOLS_MIRROR_OPERATOR` (`POSTGRES_MIRROR_ADMIN` application role, warehouse USAGE, the Snowflake application's USAGE on the instance), proved by key: the mirror procedures listed; creating a database, reading account usage and seeing Gold refused. `CREATE_MIRROR` then refused a role that does not own the instance; operator: "Fix the permission issue": ownership moved to the operator role with `COPY CURRENT GRANTS`, the role granted to ACCOUNTADMIN (grants read before and after: OWNERSHIP moved, the application's USAGE kept). The mirror then failed with "permission denied for database": the owner login granted CONNECT on `rdm`, `mdm` and `silver` to `snowflake_system`, which `harden-hosted-roles.py` now does. All in Terraform (validated) and the skills. 2026-11-19 20:34 ET
- [x] The load has finished; final sizes of the exposed tables: `mdm` 7.0 GB, `silver` about 4.2 GB, `rdm` 2.9 MB. Type scan: no blocked type, no numeric over 38 digits; JSON columns arrive as text; every table has a primary key (read from `pg_index`: `information_schema` hides keys from the reader). 2026-11-19 20:34 ET
- [x] The priced plan above is drafted from measured figures. 2026-11-19 14:30 ET
- [x] Operator: "The three priced mirror plans, which still wait on you. Approved": the three plans as drafted (tables, targets, Iceberg on Snowflake-managed storage, serverless, 60-minute refresh, the cost bounds). 2026-11-19 20:34 ET
- [x] rdm mirror created and read back: REPLICATING in a minute, 7,378 rows on both sides, target `DB_EDGARTOOLS_MIRROR_RDM.RDM.PUBLISHED_CODE`. 2026-11-19 20:34 ET
- [x] mdm mirror created and read back: both tables REPLICATING in four minutes, 3,328,964 masters and 5,306,430 identifiers on both sides; the target schema is `PUBLIC` (a mirror keeps the source schema's name). 2026-11-19 20:34 ET
- [x] The third mirror refused: the instance allows two publications (`snowflake_cdc.max_publications` 2), and `POSTGRES_SETTINGS` refuses the setting in both forms (instance unchanged, READY). Operator: "Yes" to raising it (refused by Snowflake), then "2": the rdm mirror and its target database dropped (source untouched) and the silver mirror created with the 16 tables. 2026-11-19 20:34 ET
- [ ] ~~The silver mirror REPLICATING and read back, table by table~~ superseded by ticket 04: the three store databases became one data database, so the three mirrors were dropped and one mirror of the exposed tables replaces them
- [ ] ~~The support request to raise the limit to 3 (text drafted for the operator); then the rdm mirror again~~ superseded by ticket 04: one data database needs one publication, so the limit of 2 no longer binds
- [ ] ~~`rules/exposure.yaml` and `rules/gold/gold.yaml`: a target database per layer and the schemas the mirrors keep (`PUBLIC` for mdm, `SILVER`, `RDM`); `target.verified` once all three replicate~~ superseded by ticket 04: one target database, and the mirror's table list is `sources/managed-mirror.yaml` (`verified: false` until a read-back)
- [ ] ~~The snapshot cost read from metering history against the bounds (5 credits a mirror), once the history shows it~~ deferred to ticket 04: it is read when the one mirror is created and its history shows
- [x] Learning → skill: none new. HOSTED-MIRRORING.md already holds the publication limit, the one-mirror-per-database rule and the creation order, and the three-mirror plan is retired 2026-11-21 07:41 ET

## Draft plan (not approved, not priced)

| Mirror | Source database / schema | Tables | Target database (proposed) |
|---|---|---|---|
| 1 | `mdm` / `public` | `mastering_master`, `mastering_identifier` | `DB_EDGARTOOLS_MIRROR_MDM`, schema `MDM` |
| 2 | `silver` / `silver` | the 16 silver tables of the exposure list | `DB_EDGARTOOLS_MIRROR_SILVER`, schema `SILVER` |
| 3 | `rdm` / `rdm` | `published_code` | `DB_EDGARTOOLS_MIRROR_RDM`, schema `RDM` |

- Format Iceberg, `postgres_schemas => NULL`, explicit `postgres_tables`, serverless (`warehouse => NULL`), Snowflake-managed storage
  (`external_volume => NULL`). Refresh interval: proposed 60 minutes for production (the qualification used 10); decided with the cost.
- Insert-only: none declared. Silver lands by upsert (the `nport_holding` table shows 3.8 million updates beside its inserts), so a table is not
  insert-only; the setting is left off.
- Exclusions: everything not on the list (drafts, control tables, the other 14 MDM tables), proved absent by `LIST_MIRRORED_TABLES`.

## Priced plan (drafted 2026-11-19 14:30 ET; not approved; the load is still running, so sizes grow)

Rates are the account's, read from the rate sheet (3.00 USD a credit for compute and serverless; Postgres storage 117.76 USD in the sheet's unit).

| Item | Evidence | Figure |
|---|---|---|
| Data to snapshot | store sizes now, exposed tables only | `mdm`: `mastering_master` 4.7 GB + `mastering_identifier` 1.4 GB = about 6.0 GB (the store holds 17 GB; the rest is not mirrored). `silver`: about 4.0 GB, still growing (`company_fact` 2.0 GB, `nport_holding` 1.8 GB). `rdm`: about 17 MB. About 10 GB in all |
| Instance compute | metering history, `POSTGRES_COMPUTE`, 14 days | 5.30 credits over 209 hours across both instances that ran: about 0.025 credit an hour, about 0.08 USD an hour. A mirror adds read load to this instance, not a second instance |
| Mirror apply, steady state | the qualification mirror's `SERVERLESS_TASK` line, 17 Nov | 0.015 credit in its metered hour at a 10-minute refresh and three rows: 0.045 USD an hour a mirror; three mirrors about 3.2 USD a day at 10 minutes. At 60 minutes it is expected lower and is not measured |
| Mirror storage | Iceberg, Snowflake-managed | billed as storage; at 10 GB and the highest rate in the sheet (117.76 USD per TB-month) under 1.2 USD a month. Its own rate shows only after use |
| Initial snapshot compute | not measured: the qualification held three rows | bounded, not estimated: stop and report above 5 credits (15 USD) for any one mirror, 15 credits (45 USD) in all |

- **Refresh interval:** 60 minutes for production, unmeasured; 10 minutes was the qualification's. Decided with the operator.
- **Order and deadline:** after the load ends and the instance is quiet (the snapshot reads the production instance, and a memory spike killed a load once). `rdm` first (17 MB, proves the path), then `mdm`, then `silver`, one at a time. A mirror that has not reached REPLICATING in three hours is stopped and reported.
- **Checkpoints:** every 30 minutes read `LIST_MIRRORED_TABLES` for state and the mirror's `SERVERLESS_TASK` line in metering history (the history lags up to a few hours, so the bound is read late; the snapshot state is read live).
- **Cleanup:** the plan names the exact mirror and target database to drop if a mirror is stopped; each drop has its own approval. A reset of the stores breaks the mirrors: drop or restart them first.
- **A finding for Gold.** `rules/exposure.yaml` and `rules/gold/gold.yaml` name one mirror database `DB_EDGARTOOLS_MIRROR` with three schemas.
  With three mirrors there are three target databases, so both files change to a database per layer once the targets are approved
  (the Gold sources already name a database in each source entry's layer, so only the configuration changes).
- A reset of the stores breaks a mirror: none exists now. After this load, plan any reset with the mirrors' drop or restart first.

## Answer

The three-mirror plan is retired. The rdm and mdm mirrors were built and read back equal, and the silver mirror was created, but the instance allows two publications and ticket 04 then moved mdm, rdm and silver into one data database, which needs one. The old mirrors are gone. What is left of this ticket's open parts is replaced by ticket 04 (one mirror, listed in `sources/managed-mirror.yaml`) or moved to it (the snapshot cost reading).
