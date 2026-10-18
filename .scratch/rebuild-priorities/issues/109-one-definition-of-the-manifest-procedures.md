# One definition of the manifest procedures

Priority: 109, tier 4, housekeeping (numbered after the map was charted). Map: [Rebuild priorities](../map.md).

Type: task. Status: open. Blocked by: 66 (one definition of the manifest task).

## Why

Found by the GoF review of ticket 66 (2026-10-18 12:44 ET). `REFRESH_AFTER_LOAD` and `PROCESS_RUN_MANIFEST_STREAM` are created by Terraform (`snowflake_execute.refresh_procedure` and `.stream_processor_procedure` in `infra/terraform/snowflake/modules/native_pull/main.tf`, bodies in `modules/native_pull/sql/`) and again by `infra/snowflake/sql/bootstrap/04_refresh_wrapper.sql`, which no script runs. The two bodies differ: Terraform's stream processor is JavaScript (a temp table, then a loop); `04`'s is Snowflake Scripting with the explicit cursor pattern that CLAUDE.md's Snowflake rules cite as "Live in `04_refresh_wrapper.sql`". Both were edited for the same fixes (the UTC pin, the loader role, the cursor values).

## Checklist

- [ ] Find which body prod runs (`DESCRIBE PROCEDURE` on the prod gold schema: a read, needs the operator's permission) and why the two differ
- [ ] Keep one definition (Terraform owns the task already); delete the other copy, and point CLAUDE.md's cursor rule and `08_loader_role.sql`'s comment at the one kept
- [ ] PR, CI green, merged on green
- [ ] Learning → skill
