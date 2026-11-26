# Try Decide the entity type

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/entity_type.py` only. The person pastes the rule, the record, and the doc. The page calls `classification.classify`. The result says the entity type or "held back", and shows the stored verdict `deferred` beside "held back". Do not load a kind workbook. Do not import `read_file.py`.

Invented pass: "these fields are empty" on `ticker`, with an empty ticker, returns held back. A rule with no matching step and no "otherwise" returns the engine's refusal.

Known leftover: `classify` already loads `rules/identifiers/*.yaml` at import. This ticket does not change that loader.

## Checklist

- [x] `entity_type.py` is the only production file this ticket adds. `tests/unit/test_rules_try_entity_type.py` is new. 2026-11-25 21:54 ET
- [x] An empty ticker with "these fields are empty" returns held back. `tests/unit/test_rules_try_entity_type.py`. 2026-11-25 21:54 ET
- [x] A rule with no match and no "otherwise" returns the engine's refusal. `tests/unit/test_rules_try_entity_type.py`. 2026-11-25 21:54 ET
- [x] No kind workbook is loaded. `tests/unit/test_rules_try_entity_type.py` forbids opening a file after the first call. 2026-11-25 21:54 ET
- [x] Learning → skill: none. The family is one call to the existing classifier. 2026-11-25 21:54 ET

## Answer

`entity_type` shows the title "Decide the entity type" and two inputs: the record as JSON and the doc (the lists and normalizers the rule names) as JSON, which may be empty. The rule box holds the classification rule as JSON. Try calls `edgar_warehouse.mdm.classification.classify` and returns `{"entity type": "<kind>"}` when the verdict is a kind, or `{"held back": "<stored verdict>"}` (`deferred` or `entity_undetermined`) when it is not. A rule or record or doc that is not JSON or not an object, steps that are not a list of steps with lists of tests, and anything the engine refuses (no `otherwise` step, an unknown test, a list the doc does not hold, an undeclared verdict) return `{"refused": "..."}`. The invented empty ticker with "these fields are empty" returns `{"held back": "deferred"}`.

## Comments

