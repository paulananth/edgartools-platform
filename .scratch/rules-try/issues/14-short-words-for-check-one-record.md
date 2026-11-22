# Accept short words for Check one record

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/check_record_full.py` only. This file can merge before ticket 13. The page ignores it until `check_record.py` exists.

- is present → `present@1`
- hold the record out → `exception`
- keep off matching → `withhold`
- count the failure → `flag`
- in the pinned code set → `in_reference@1`

## Checklist

- [ ] `check_record_full.py` is the only file this ticket adds
- [ ] The missing-name case written in these words matches ticket 13
- [ ] The shown block includes the version string the person types
- [ ] Learning → skill

## Comments

