"""Operational bookkeeping store (checkpoints, sync-state, leases, run audit trail).

DuckDB Retirement Cutover Ticket 02: these 11 tables carry no SEC content and
no MDM entity data -- they are the warehouse runtime's own operational
bookkeeping (checkpoints, leases, sync/parse/pipeline run audit rows, the gold
publish manifest, and reconcile findings). They move to Snowflake's native
Postgres service, architecturally the same shape as `edgar_warehouse.mdm`'s
own Postgres store, just a different table set and a dedicated connection.
"""
