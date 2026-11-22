# Accept short words for Decide the entity type

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/entity_type_full.py` only. This file can merge before ticket 16. The page ignores it until `entity_type.py` exists.

- field is one of → `field_in_set@1`
- these fields are empty → `fields_all_empty@1`
- name tokens match → `token_match@1`, `token_match@2`
- held back → `deferred` (no master is created)
- probable entity type → `probable_kind` (a queue label, not a master)
- otherwise → `otherwise`

## Checklist

- [ ] `entity_type_full.py` is the only file this ticket adds
- [ ] The empty-ticker case written as "these fields are empty" matches ticket 16
- [ ] Learning → skill

## Comments

