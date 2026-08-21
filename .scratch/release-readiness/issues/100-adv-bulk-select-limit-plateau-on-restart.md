# adv_bulk.py's bare SELECT * LIMIT N plateaus on restart, like Ticket 94's run_companies bug

Type: task
Status: open
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

Not yet answered — filed here rather than fixed speculatively. Whoever
picks this up should first confirm live impact: check whether any
production `mdm run`/`load_history` invocation actually passes a `limit`
to `run_advisers`/`run_funds` (a scoped/bounded run, not the default
unlimited `mdm run --entity-type all`) — if `limit` is never set in
practice, this bug has zero live effect and the fix can wait indefinitely.
