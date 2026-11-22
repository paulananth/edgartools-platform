# Accept short words for a rule-decided entity type

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/prepare_by_type_rule_full.py` only. Same words as ticket 32, plus "entity type rule" → `classification`. This is the only file that accepts "entity type rule". This file can merge before ticket 34. The page ignores it until `prepare_by_type_rule.py` exists.

## Checklist

- [ ] `prepare_by_type_rule_full.py` is the only file this ticket adds
- [ ] The rule-decided case written with "entity type rule" matches ticket 34
- [ ] No other full-rule file accepts "entity type rule"
- [ ] Learning → skill

## Comments

