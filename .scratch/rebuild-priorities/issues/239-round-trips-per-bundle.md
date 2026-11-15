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

## Checklist

- [ ] The statements of one bundle counted by a committed command (local store, statement logging), so a change shows its effect as a count
- [ ] The Change Journal appends a bundle's events in one statement (`unnest` of an array through `journal.record_event`), the same receipts in the same order
- [ ] A checkout pings only a connection idle longer than a bound, not every checkout; a dropped hosted connection is still found
- [ ] A worker's commands reuse its connections where one process serves several
- [ ] A persons bundle measured again, local (statements) and hosted (seconds)
- [ ] Learning → skill
