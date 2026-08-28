# 02 — Move Operational Bookkeeping Tables to Snowflake's Native Postgres Service

**What to build:** DuckDB Retirement's Ticket 08 decided these 11 tables —
checkpoints, sync-state, leases, and the run audit trail, none of them SEC
content or MDM data — have no Snowflake landing-zone replication path today
and must move to Snowflake's native Postgres service, reusing the exact
provisioning pattern `bootstrap-prod-mdm.sh` already proved for MDM's
operational store:

- `sec_company_sync_state`
- `sec_source_checkpoint`
- `pipeline_run`
- `pipeline_run_lease`
- `sec_sync_run`
- `sec_parse_run`
- `discovery_checkpoint`
- `sec_daily_index_checkpoint`
- `stg_daily_index_filing`
- `gold_manifest`
- `sec_reconcile_finding`

(`schema_migration`, originally counted alongside these 12, is excluded —
it's `SilverDatabase`'s own internal DuckDB-migration ledger with no meaning
once DuckDB itself is gone; it does not migrate anywhere.)

Provision a dedicated Snowflake Postgres instance (or a schema within one, if
that's the pattern MDM's own instance uses) via a committed, re-runnable
script — not a manual one-off session, per this repo's own "MDM Snowflake
mirror schema lost on cutover" incident. Wire every reader/writer of these 11
tables (checkpoints read at lease-acquisition time, sync-state read at
window-selection time, etc.) to the new store.

**Operator-accepted cost, stated explicitly so it isn't rediscovered as a
surprise during rollout:** the new store starts **empty**, not migrated from
existing DuckDB state. Every currently paused/completed CIK reverts to
pending and becomes eligible for full re-bootstrap on the first post-cutover
run — the same reactivation hazard `seed-universe-narrow-hydrate`'s Ticket 05
flagged, now happening deliberately, platform-wide, by explicit operator
choice (DuckDB Retirement map, Ticket 08's answer).

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] A committed, re-runnable provisioning script creates the new Postgres
      store (schema/tables) for all 11 tables, mirroring
      `bootstrap-prod-mdm.sh`'s pattern
- [ ] Every reader/writer of each of the 11 tables is repointed at the new
      store (grep confirms zero remaining DuckDB reads/writes for these
      table names)
- [ ] Snowflake grants for whichever role needs read/write access are
      applied additively (no `REVOKE CURRENT GRANTS`, per this repo's
      "Manifest-pipeline ownership" incident lesson)
- [ ] Tests covering lease acquisition, checkpoint read/write, and run-audit
      writes pass against the new store
- [ ] The empty-start behavior (every CIK reverts to pending) is documented
      in the deploy runbook, not just this ticket, so whoever runs the
      cutover isn't surprised by the reactivation scale
