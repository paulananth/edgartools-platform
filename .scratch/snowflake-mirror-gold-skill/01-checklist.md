# Snowflake mirror to Gold skill update

- [x] Describe the selected PostgreSQL mirror → Iceberg → dbt Gold flow and retain its pending qualification gates; validated with 125 focused skill/documentation checks. 2026-11-15 20:53 ET
- [x] Add Snowflake database retirement preflight for objects, grants, mirror ownership, retention and network-rule policy dependencies; verified against the non-destructive production drop rejection. 2026-11-15 20:53 ET
- [ ] ~~Drop the requested production database~~ deferred until the network-rule association can be relocated or removed without changing the production Postgres access policy without authorization.
- [x] Learning → skill: record the mirror-to-Gold target flow and require network-rule association checks before dropping a database. 2026-11-15 20:53 ET
