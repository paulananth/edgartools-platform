# Try Prepare the MDM record

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/prepare_record.py` only. The person pastes a contract with a fixed entity type and no classification key. The page calls `normalize`. A contract that contains `classification` is refused before `normalize` runs. The word on the page for `kind` is entity type.

Invented pass: one row, a fixed entity type, and one identifier come back as that entity type, that record key, and that identifier. A row missing the key returns the engine's refusal.

## Checklist

- [ ] `prepare_record.py` is the only file this ticket adds
- [ ] The fixed-type row produces that entity type, record key, and identifier
- [ ] A missing key is refused
- [ ] A contract that contains classification is refused before `normalize`
- [ ] Learning → skill

## Comments

