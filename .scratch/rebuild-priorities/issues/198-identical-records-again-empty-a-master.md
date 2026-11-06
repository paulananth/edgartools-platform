# 198: Identical records arriving again empty a master

Priority: 198. Map: [Rebuild priorities](../map.md). Opened 2026-11-06 06:52 ET. Found by comparing the three-operation prototype with the engine (ticket 197).

Type: task. Status: open. Blocked by: none.

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

How the batch came to lose the members is not found yet: `read_affected_records` and `prepare_master_records` are the next place to look. Ticket 197's open part on bundle 11, loaded again though stored, may be the same path.

## Checklist

- [x] Found, measured and traced to one batch (2026-11-06 06:52 ET).
- [ ] Reproduce with a test: a batch of records already mastered changes no master.
- [ ] Find the cause and fix it.
- [ ] Repair the 122 masters, and let the 72 GLEIF records match.
- [ ] Check no other batch did this after the repair.
- [ ] Learning → skill.
