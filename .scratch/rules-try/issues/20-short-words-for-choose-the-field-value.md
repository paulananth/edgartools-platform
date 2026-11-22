# Accept short words for Choose the field value

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/field_value_full.py` only. This file can merge before ticket 19. The page ignores it until `field_value.py` exists.

- source order → `defaults.sources`
- this field's order → `fields.<name>.sources`
- may blank the field → `clear_sources`
- ignore older than → `max_age_days`

## Checklist

- [ ] `field_value_full.py` is the only file this ticket adds
- [ ] The directory-then-register case written in these words matches ticket 19
- [ ] Learning → skill

## Comments

