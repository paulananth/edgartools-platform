# The create plan for the three mirrors, after the first load

Status: open
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
- [ ] The mirror's grant sequence (the mirror sub-skill) checked against the instance
- [ ] The load has finished and its counts are read (table sizes decide the snapshot cost)
- [x] The priced plan above is drafted from measured figures. 2026-11-19 14:30 ET
- [ ] Present the three create plans with their costs for the operator's approval of each, once the load has finished and the sizes are final
- [ ] Create each mirror, read it back (`LIST_MIRRORED_TABLES`, `SHOW ICEBERG TABLES`, types, keys, exact decimals) and set `rules/exposure.yaml` `target.verified`
- [ ] Learning → skill: HOSTED-MIRRORING.md, once a mirror is built

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
