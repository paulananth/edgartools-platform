# Try Check one record

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/check_record.py` only. The person pastes the quality block, the fields, and the matching input. The page calls `quality.apply`. A held-out record is `{"held out":"quality_<id>"}`, and the page shows the stored word `exception` beside "held out".

Invented pass: a present name passes. A missing name written as "is present" and "hold the record out" is held out.

Known leftover: if the paste itself uses `in_reference@1` or `in_hierarchy@1`, `apply` already reads `rules/reference`. This ticket does not add another read. The test uses "is present" only.

## Checklist

- [ ] `check_record.py` is the only file this ticket adds
- [ ] An invented present name passes
- [ ] A missing name is held out, with `exception` shown beside "held out"
- [ ] The test does not use an in-reference check
- [ ] Learning → skill

## Comments

