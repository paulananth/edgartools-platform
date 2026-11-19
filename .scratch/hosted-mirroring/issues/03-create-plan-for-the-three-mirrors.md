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
- [ ] Present the three create plans with their costs for the operator's approval of each
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
- Insert-only: the append silver tables (the guide's insert-only option) are named when their sizes are known.
- Exclusions: everything not on the list, drafts and the control tables, proved absent by `LIST_MIRRORED_TABLES`.
- Cost boundary, deadline and cleanup plan: not drafted. They need the pre-flight (current credit rates, instance family), the load's final
  table sizes and a stated deadline. A mirror's snapshot and apply are billed, so each bound is priced before create and a checkpoint is
  kept every 30 minutes (ticket `single-iceberg-mirror/02`).
- **A finding for Gold.** `rules/exposure.yaml` and `rules/gold/gold.yaml` name one mirror database `DB_EDGARTOOLS_MIRROR` with three schemas.
  With three mirrors there are three target databases, so both files change to a database per layer once the targets are approved
  (the Gold sources already name a database in each source entry's layer, so only the configuration changes).
- A reset of the stores breaks a mirror: none exists now. After this load, plan any reset with the mirrors' drop or restart first.
