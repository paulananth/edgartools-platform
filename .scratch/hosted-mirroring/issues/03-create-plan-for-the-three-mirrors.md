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
- [ ] A read-only Snowflake connection for the pre-flight (instance family `STANDARD_*` or `HIGHMEM_*`, version, the mirror grants) and the current credit rates; the operator names it, never the admin account, `edgartools-prod` or `snowconn`
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
