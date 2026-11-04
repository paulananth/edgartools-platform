# One definition of the manifest procedures

Priority: 109, tier 4, housekeeping (numbered after the map was charted). Map: [Rebuild priorities](../map.md).

Type: task. Status: resolved (2026-11-03 18:59 ET). Blocked by: 66 (one definition of the manifest task).

## Why

Found by the GoF review of ticket 66 (2026-10-18 12:44 ET). `REFRESH_AFTER_LOAD` and `PROCESS_RUN_MANIFEST_STREAM` are created by Terraform (`snowflake_execute.refresh_procedure` and `.stream_processor_procedure` in `infra/terraform/snowflake/modules/native_pull/main.tf`, bodies in `modules/native_pull/sql/`) and again by `infra/snowflake/sql/bootstrap/04_refresh_wrapper.sql`, which no script runs. The two bodies differ: Terraform's stream processor is JavaScript (a temp table, then a loop); `04`'s is Snowflake Scripting with the explicit cursor pattern that CLAUDE.md's Snowflake rules cite as "Live in `04_refresh_wrapper.sql`". Both were edited for the same fixes (the UTC pin, the loader role, the cursor values).

## Checklist

- [ ] ~~Find which body prod runs (`DESCRIBE PROCEDURE` on prod)~~ not needed (2026-11-03 18:59 ET): no production Snowflake now (operator, 2026-11-03), and the repo answers it: Terraform creates both procedures and the task; no script runs `04_refresh_wrapper.sql`
- [x] Keep one definition (2026-11-03 18:59 ET): Terraform's (`native_pull/sql/`) kept; `04_refresh_wrapper.sql` deleted; `08_loader_role.sql`'s comment and the `aws-snowflake-operations` skill rule point at the one kept (CLAUDE.md no longer holds the cursor rule); checked by `git grep` (no other reference to the file) and the genericity and guide-path lints
- [x] PR, CI green, merged on green (2026-11-03 18:59 ET): this PR is the record, merged by the watcher on green CI
- [x] Learning → skill (2026-11-03 18:59 ET): `skills/aws-snowflake-operations/SKILL.md`, "Snowflake rules learned from incidents", first bullet: the manifest procedures have one definition, in Terraform; never a second copy in bootstrap SQL
