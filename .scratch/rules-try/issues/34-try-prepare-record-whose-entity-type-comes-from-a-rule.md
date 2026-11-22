# Try Prepare a record whose entity type comes from a rule

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/prepare_by_type_rule.py` only. The person pastes a contract that has `classification`, and the policy. The page calls `normalize`. Do not edit `prepare_record.py`. Do not load `company.yaml`.

Invented pass: the row receives the entity type the pasted rule decides.

## Checklist

- [ ] `prepare_by_type_rule.py` is the only file this ticket adds
- [ ] The row receives the entity type the pasted rule decides
- [ ] `prepare_record.py` is not edited
- [ ] `company.yaml` is not loaded
- [ ] Learning → skill

## Comments

