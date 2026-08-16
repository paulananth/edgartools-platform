# Decide the Production Write-Path Cutover Sequence

Type: grilling
Status: open
Blocked by: 02, 03, 04

## Question

The closed silver-snowflake-migration map's Ticket 02 decided the write
path dual-writes today: parse fans out in-process to both DuckDB silver
and the Snowflake landing zone in parallel. This map's destination is
Snowflake-only — DuckDB stops being written entirely. That can only happen
safely once every reader currently depending on DuckDB has moved off it:
MDM ([Ticket 02](02-decide-mdm-reader-replacement-mechanics.md)), gold
([Ticket 03](03-decide-gold-builder-retirement-mechanics.md)), and
`bootstrap-batch` ([Ticket 04](04-decide-bootstrap-batch-sharding-fate.md))
— hence this ticket is blocked by all three.

Decide, once those are settled: the actual mechanics of turning off the
DuckDB write in `_run_submissions_bronze_then_silver`/
`_apply_submission_snapshot_to_silver` (`warehouse_orchestrator.py:3085`/
`:4820`) — a flag-gated transition (both writes continue for a defined
period as a safety net) or an atomic code change once all three consumers
have confirmed their cutover? What happens to an `load_history`/
`daily_incremental` execution that's *mid-flight* across the cutover
boundary (a window that started under dual-write, finishes after DuckDB
writes are removed)? What's the rollback story if a production issue
surfaces post-cutover, given DuckDB fully leaves the codebase per this
map's scope — is rollback "revert the commit and redeploy" (no live
toggle), and is that an acceptable answer given "the whole platform's
silver data" is what's at stake? Finally, decide disposition of the
existing `s3://edgartools-prod-warehouse-*/warehouse/silver/sec/
silver.duckdb` file and its shards once writes stop — deleted immediately,
archived for a retention period, or left in place under an S3 lifecycle
rule (matching this repo's existing precedent, CLAUDE.md's "S3 lifecycle
rule for warehouse/silver/").

## Deliverable

A decided cutover mechanism (flag-gated vs. atomic), an answer for
mid-flight executions crossing the boundary, an explicit rollback story,
and a decided disposition for the existing DuckDB files in S3.
