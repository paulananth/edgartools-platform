# 04 — Audit load_history's internal large-profile states for the unscoped-load shape

Type: task
Status: open

## Question

`load_history`'s state machine (`write_load_history_definition`,
`infra/scripts/deploy-aws-application.sh`) runs several of its own states
on `wh_large_arn` beyond the already-covered `bootstrap-next`/
`seed-universe` (task-profile-consolidation map, tickets 06/07, both
resolved): `ComputeWindows` (window planning, ~line 2625), 3 per-window
fundamentals fetches — `fetch-entity-facts`, `fetch-per-filing-fundamentals`,
`fetch-thirteenf-holdings` (~lines 2771/2850/2888) — `ReleaseSecFetchLease`
(~line 3711), and `ReduceIdentityRefresh` (~line 3773). None of these six
have been checked against the MANAGES_FUND-shape risk. Audit each; fix any
genuine gap the same way MANAGES_FUND/INSTITUTIONAL_HOLDS were.

Also resolve a discrepancy noted while charting this map: 2 call sites
(~lines 3487, ~4129) still hardcode `wh_large_arn` directly for a
`SeedUniverse` state, seemingly bypassing `command_task_profile()`'s
`seed-universe` → `"medium"` decision (task-profile-consolidation ticket
07). Confirm whether these are current, live state-machine definitions or
dead/superseded code before treating this as a real discrepancy — if
live, decide whether they need to be routed through the shared lookup
(task-profile-consolidation's own established pattern) or whether there's
a load_history-specific reason for the divergence that ticket 07 didn't
already rule out.

`ComputeWindows` and `ReduceIdentityRefresh` are the two most likely to
touch a shared dataset before per-window scoping is established (window
planning necessarily looks at more than one window's worth of data) —
prioritize those first if time is limited.

## Blocked by

None — can start immediately.
