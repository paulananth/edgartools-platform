# Try Link two masters

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/link_masters.py` only. The person pastes claims, state, entities, as-of time, and types. The page calls `project` with those arguments. Do not call `types_of`. Do not read `rules/reference`. A link does not create a master.

Invented pass: pasted endpoints that resolve emit one link. A pasted claim with no start time returns the engine's wait.

## Checklist

- [ ] `link_masters.py` is the only file this ticket adds
- [ ] Resolved ends emit one link
- [ ] A missing start waits
- [ ] `types_of` is not called
- [ ] Learning → skill

## Comments

