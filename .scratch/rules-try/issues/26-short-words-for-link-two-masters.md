# Accept short words for Link two masters

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/link_masters_full.py` only. A missing end stays the engine's wait. No end is invented from a later file. This file can merge before ticket 25. The page ignores it until `link_masters.py` exists.

- link type → `type`
- other master's key → `target_key`
- link starts → `valid_from`
- link ends → `valid_to`

## Checklist

- [ ] `link_masters_full.py` is the only file this ticket adds
- [ ] The resolved-ends case written in these words matches ticket 25
- [ ] A missing end is not invented
- [ ] Learning → skill

## Comments

