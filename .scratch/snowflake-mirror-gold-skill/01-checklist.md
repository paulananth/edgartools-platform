# Snowflake mirror to Gold skill update

- [x] Describe the selected PostgreSQL mirror → Iceberg → dbt Gold flow and retain its pending qualification gates; validated with 125 focused skill/documentation checks. 2026-11-15 20:53 ET
- [x] Add Snowflake database retirement preflight for objects, grants, mirror ownership, retention and network-rule policy dependencies; verified against the non-destructive production drop rejection. 2026-11-15 20:53 ET
- [x] Preserve the existing Postgres ingress rule in `DB_EDGARTOOLS_GOLD.CONTROL`, verify the policy and instance, confirm Postgres connectivity, drop `EDGARTOOLS_PROD`, and verify the database is absent. 2026-11-15 21:17 ET
- [x] Learning → skill: record the mirror-to-Gold target flow and require network-rule association checks before dropping a database. 2026-11-15 20:53 ET
