# 19: MySQL silver lands without a staging table

Status: open
Type: task

Ticket 17 removed the staging table from the PostgreSQL silver writer (operator, 2026-11-22: "no staging table needed remember 7 wastes").
MySQL still stages each delivery in a permanent staging table made at registration (`DatabaseSink._write_mysql`): no DDL at run time,
but every row moves twice, and the delivery holds the table's lock while it stages. MySQL has no `ON CONFLICT` and no `unnest`, so the
PostgreSQL path does not carry over as is.

## Checklist

- [ ] Choose MySQL's per-batch form: `INSERT ... ON DUPLICATE KEY UPDATE` on the `_silver_key` hash, or a `JSON_TABLE` of each batch
      joined to the table, keeping append's refusal of a changed row and the snapshot's removal of keys it did not deliver
- [ ] Failing test first at `land`, then the MySQL silver storage and recovery tests (`ADAPTER_ENGINES=mysql`)
- [ ] Drop the staging table from registration and its `lock_silver_table` use where no longer needed
- [ ] Learning → skill: mdm-engineering's MySQL line, or "none"
