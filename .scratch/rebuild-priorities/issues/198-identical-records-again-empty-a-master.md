# 198: Identical records arriving again empty a master

Priority: 198. Map: [Rebuild priorities](../map.md). Opened 2026-11-06 06:52 ET. Found by comparing the three-operation prototype with the engine (ticket 197).

Type: task. Status: resolved. Blocked by: none.

## Question

Why does a batch of records already mastered write their masters back with no fields, no identifiers and no members, and how is that stopped and repaired?

## Found

| Fact | Measured |
|---|---|
| Masters with no members | 122 of 428,763, all Company |
| Status of those masters | `accepted` |
| Their first version (batch generation 4) | members 1, fields 5, identifiers 1 |
| Their current version (batch generation 150) | members 0, fields 0, identifiers 0 |
| What generation 150 carried | 122 `sec.company` records, 122 of 122 the same record ids as generation 4, plus 389 deferred records |
| Their bind decisions | Still stored, all 122 |
| GLEIF records left unmatched because of it | 72 of the 3,186 + 72 that pass the name rules |

The master read for matching sees no bound record on an emptied master, so a name match to it never lands (inferred from the 72 of 72 targets; not yet tested on its own).

## Cause

A bundle's `as_of` is fixed when it starts. Replay keeps only decisions dated at or before its clock (`identity.rs:70`). Generation 150 ran at 03:29:08 UTC and the binds were stamped 03:32:20 UTC, because a bundle started later had stored first. To that batch the binds had not happened, so their masters had no members. The same clock filtered withheld values.

## Fix

`merge.py` replays at the time of the write, the later of `as_of` and every stored decision in scope. `withheld_by` no longer takes a clock. A reading's own effective date and field freshness still use `as_of`.

The test `older_clock` runs on the storage-adapter matrix. MySQL: failed on the old code at `stored_master(...) == before`, passed on the new. PostgreSQL: the same in `test_a_slower_bundle_keeps_stored_decisions.py`. SQL Server refuses the prepared store, so no merge runs there.

## Repair

Through the Merge Stage on the shared store, rehearsed first on the benchmark copy. The records were replayed with no rule proposals, since a rule saw them as unbound and proposed a new bind, which replay refused as a move.

| Check | Result |
|---|---|
| Masters restored | 122 of 122 |
| Same members, identifiers and field values as before generation 150 | 122 of 122 |
| Empty masters left | 0 of 428,763 |
| New masters | 0 |
| GLEIF records matched afterwards, by the real rules | 72 of 72, same rule as the prototype |
| Compared with the prototype | 8,361 of 8,361 masters, 67,034 of 67,034 fields, 3,258 of 3,258 name matches |

## Checklist

- [x] Found, measured and traced to one batch (2026-11-06 06:52 ET).
- [x] Reproduce with a test: a batch of records already mastered changes no master. Failed before the fix on PostgreSQL and MySQL (2026-11-06 07:23 ET).
- [x] Find the cause and fix it: PR 1452 (2026-11-06 07:23 ET).
- [x] Repair the 122 masters, and let the 72 GLEIF records match: live check above (2026-11-06 07:10 ET).
- [x] Check no other batch did this after the repair: 0 empty masters of 428,763 (2026-11-06 07:12 ET).
- [x] Learning → skill: `mdm-engineering`, "The Merge Stage": a batch replays at the time of its write (2026-11-06 07:23 ET).
