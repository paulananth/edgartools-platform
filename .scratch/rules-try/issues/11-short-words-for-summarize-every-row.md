# Accept short words for Summarize every row

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/whole_set_full.py` only. Accept only: how many rows, distinct values, most frequent. Refuse "how many at this path". This file can merge before ticket 10. The page ignores it until `whole_set.py` exists.

## Checklist

- [ ] `whole_set_full.py` is the only file this ticket adds
- [ ] The three-row case written in those words matches ticket 10
- [ ] "how many at this path" is refused
- [ ] Learning → skill

## Comments

