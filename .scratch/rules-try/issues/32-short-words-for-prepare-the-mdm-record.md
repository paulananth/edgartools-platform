# Accept short words for Prepare the MDM record

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/prepare_record_full.py` only. "entity type rule" is refused here. Ticket 35 is the only file that accepts it. This file can merge before ticket 31. The page ignores it until `prepare_record.py` exists.

- entity type → `kind`
- record key → the adapter's record key
- identifier → the adapter's identifier list
- lookup only → a cross-reference that does not match by itself

## Checklist

- [ ] `prepare_record_full.py` is the only file this ticket adds
- [ ] The fixed-type case written in these words matches ticket 31
- [ ] "entity type rule" is refused
- [ ] Learning → skill

## Comments

