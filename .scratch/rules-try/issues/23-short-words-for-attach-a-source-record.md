# Accept short words for Attach a source record

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/attach_record_full.py` only. A word for combining two existing masters is refused. That decision stays on `rules test`. "attach" here is this family only. Ticket 08's "attach" means grouped rows. The page title tells them apart, and each file refuses the other family's words.

This file can merge before ticket 22. The page ignores it until `attach_record.py` exists.

- same identifier → `identifier_match@1`
- how many that identifier allows → `identifier_cardinality@1`
- attach → `bind`
- create a master → `mint`
- send to review → the review outcome

## Checklist

- [ ] `attach_record_full.py` is the only file this ticket adds
- [ ] The one-master and two-master cases written in these words match ticket 22
- [ ] A word for combining two existing masters is refused
- [ ] Learning → skill

## Comments

