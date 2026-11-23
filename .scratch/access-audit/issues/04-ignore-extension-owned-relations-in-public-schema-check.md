# Exclude extension-owned relations from the public-schema audit

Status: open
Type: task

The PostgreSQL schema audit counted the `pg_stat_statements` extension's two public views in each hosted database as application objects. This makes the initialization readiness gate fail `SCH.postgres` after a clean database reset. Exclude extension-owned relations and functions while continuing to flag application-owned public objects.

## Acceptance

- [ ] A disposable PostgreSQL 16 instance with only the `pg_stat_statements` extension in `public` passes `SCH.postgres`.
- [ ] Application-owned tables, views, sequences and functions in either database fail `SCH.postgres`.
- [ ] No public objects passes `SCH.postgres`.
- [ ] The hosted readiness audit passes after the fix is merged.
