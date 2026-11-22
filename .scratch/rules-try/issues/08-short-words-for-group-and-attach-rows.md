# Accept short words for Group and attach rows

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/group_rows_full.py` only. "how many at this path" is refused here. That phrase belongs to ticket 05. This file can merge before ticket 07. The page ignores it until `group_rows.py` exists.

- list the values → `collect`
- one flat list → `collect_flat`
- first row, last row → `first`, `last`
- exactly one row → `one`
- how many rows → `count` on a reduction
- distinct values → `members`
- most frequent → `most` (blank when two tie)
- attach → `joins` (grouped rows, not a source record)

## Checklist

- [ ] `group_rows_full.py` is the only file this ticket adds
- [ ] The R1 case written with "list the values" and "attach" matches ticket 07
- [ ] "how many at this path" is refused
- [ ] Learning → skill

## Comments

