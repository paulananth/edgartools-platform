# 239: A bundle makes about 2,750 statements; on a hosted store each costs a round trip

Type: task. Status: open. Blocked by: none. Found by ticket 233's measurement (operator, 2026-11-15: "Start ticket 233").

## Question

Why does a persons bundle take 110 s on the hosted store and 8 to 14 s on a local one, and which statements can go?

## Evidence (ticket 233, "Measured again")

A statement log of 4 local persons bundles, grouped by shape (counts only): 10,985 statements, about 2,750 a bundle, in 156
sessions. At 43 ms to the hosted store that is 118 s, the bundle's 110 s.

| Per bundle | Statements | Why |
|---|---|---|
| `journal.record_event` | 512 | the `processed` step appends one event a file, one call each (38 s hosted) |
| `SELECT 1` with its BEGIN and ROLLBACK | about 800 | `pool_pre_ping` on every checkout of Bookkeeping, Change Journal and Rules |
| New sessions | about 36 sessions, 7 setup statements each, and the TLS handshake | one connection a command |
| The merge's own statements | about 100 | already set-based |

## Remaining after the first two changes

Per bundle, locally: 1,665 statements in 36 sessions: about 340 BEGIN and 230 ROLLBACK (a read-only checkout ends in a rollback), 720
reads, 55 liveness checks left and the session setup. Next: reuse a worker's connections, and read-only checkouts that
send no BEGIN or ROLLBACK.

## Checklist

- [x] The statements of one bundle counted by a committed command (`skills/data-operations/scripts/count_statements.py`: a local store with statement logging, grouped by shape) so a change shows as a count (2026-11-15 15:09 ET)
- [x] The Change Journal appends a bundle's events in one statement (`unnest` of an array through `journal.record_event`) on PostgreSQL, the same receipts; MySQL and SQL Server unchanged. Test: 60 events were 60 statements, now 1 (`test_a_file_set_is_recorded_in_one_statement_on_postgresql`) (2026-11-15 15:09 ET)
- [x] A checkout no longer pings: the three stores' engines replace a connection older than 30 s at checkout (`pool_recycle`), which finds one dropped while idle with no statement; a shared helper was refused by the journal's independence rule and is not needed. Tests: 4 pings in 5 checkouts, now 0; an aged connection is replaced and a young one reused (`tests/unit/test_engine_checkout.py`) (2026-11-15 15:09 ET)
- [ ] A worker's commands reuse its connections where one process serves several
- [ ] A persons bundle measured again: local, 2,750 statements a bundle before and 1,665 after (5 bundles each, same capture); hosted seconds after the persons lane restarts on this code
- [ ] Learning → skill
