# Try Decide the entity type

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/entity_type.py` only. The person pastes the rule, the record, and the doc. The page calls `classification.classify`. The result says the entity type or "held back", and shows the stored verdict `deferred` beside "held back". Do not load a kind workbook. Do not import `read_file.py`.

Invented pass: "these fields are empty" on `ticker`, with an empty ticker, returns held back. A rule with no matching step and no "otherwise" returns the engine's refusal.

Known leftover: `classify` already loads `rules/identifiers/*.yaml` at import. This ticket does not change that loader.

## Checklist

- [ ] `entity_type.py` is the only file this ticket adds
- [ ] An empty ticker with "these fields are empty" returns held back
- [ ] A rule with no match and no "otherwise" returns the engine's refusal
- [ ] No kind workbook is loaded
- [ ] Learning → skill

## Comments

