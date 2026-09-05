# adv_bulk.py's bare SELECT * LIMIT N plateaus on restart, like Ticket 94's run_companies bug

Type: task
Status: resolved (2026-09-05) — see `## Answer`; fix tracked elsewhere, not here.
Blocked by: none

## Question

Discovered incidentally while auditing MDM resolvers for the
skip-if-unchanged bug class (`.scratch/mdm-resolver-skip-unchanged/`,
Ticket 01). `edgar_warehouse/mdm/adv_bulk.py`'s `resolve_advisers_bulk`
(`sql = "SELECT * FROM sec_adv_filing"`, `+= " LIMIT {int(limit)}"`) and
`resolve_funds_bulk` (`sql = "SELECT * FROM sec_adv_private_fund"`, same
`LIMIT` suffix) have no `ORDER BY` and no exclusion of already-resolved
rows. This is the identical shape Ticket 94 found and fixed for
`run_companies()`: a caller that passes the same `limit` on every restart
re-fetches the same first N rows every time, making zero cumulative
progress across restarts — not the append-only-staging bug Ticket 94 was
originally about, a different, adjacent correctness gap in the same
"bare bounded SELECT" pattern.

Unlike the skip-if-unchanged bug class, this one is real regardless of
content-hash dedup: `_existing_source_ids()` already prevents duplicate
stage rows for a source_id seen before (so no unbounded stage-row
growth), but if `limit` is set and the same N filing rows keep winning the
unordered `SELECT * LIMIT N`, a restarted `mdm run` can never reach rows
past the Nth — the dedup check just makes each repeat call a no-op rather
than a progress-losing plateau being visible as duplicate rows.

Does this need the same fix Ticket 94 applied to `run_companies()` (port
the growing-window/stable-order pattern, excluding already-resolved
identities), and if so, on what timeline relative to this map's other
open work?

## Answer

**Live impact confirmed 2026-09-05** (raised during the
`fundamentals-daily-integration` map's grilling round on whether ADV is
wired for diff processing into `daily_incremental`): `daily_incremental`'s
`RunMdmChain` calls `mdm mastering --entity-type all --limit 100` every
single day (`MDM_RUN_LIMIT` defaults to 100,
`deploy-aws-application.sh:1882`), and `MDMPipeline.run_all(limit=100)`
forwards that exact `limit` straight into `run_advisers(limit=limit)` and
`run_funds(limit=limit)` (`pipeline.py:2065,2073`) — so this is not a
theoretical exposure, it fires on every production `daily_incremental`
execution. `limit` is never unset in practice for this path.

Picked up and tracked as
[Ticket 06 on the `fundamentals-daily-integration` map](../../fundamentals-daily-integration/issues/06-fix-adv-bulk-select-limit-plateau.md)
rather than fixed here — the user chose to fix it there, alongside that
map's other `daily_incremental` incremental-scoping work, rather than
under release-readiness. See that ticket for the fix design and status.
