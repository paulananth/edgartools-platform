# Exclude extension-owned relations from the public-schema audit

Status: resolved
Type: task

The PostgreSQL schema audit counted the `pg_stat_statements` extension's two public views in each hosted database as application objects. This makes the initialization readiness gate fail `SCH.postgres` after a clean database reset. Exclude extension-owned relations and functions while continuing to flag application-owned public objects.

## Acceptance

- [x] A disposable PostgreSQL 16 instance with only the `pg_stat_statements` extension in `public` passes `SCH.postgres`.
- [x] Application-owned tables, views, sequences and functions in either database fail `SCH.postgres`.
- [x] No public objects passes `SCH.postgres`.
- [x] The hosted readiness audit passes after the fix is merged: 13/13 checks returned `READY` on `main` commit `308e6542` (2026-11-22 22:42 ET).
