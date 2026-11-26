# Accept short words for Decide the entity type

Type: task
Status: resolved
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

- [x] `entity_type_full.py` is the only production file this ticket adds. `tests/unit/test_rules_try_entity_type_full.py` is new. 2026-11-25 22:43 ET
- [x] The empty-ticker case written as "these fields are empty" matches ticket 16. `tests/unit/test_rules_try_entity_type_full.py` tries the shown document on the `entity_type` family. 2026-11-25 22:43 ET
- [x] Learning → skill: none. The words are one table in one file. 2026-11-25 22:43 ET

## Answer

`explain(rule)` takes a short classification rule and returns `{"lines": [{"word", "stored"}, ...], "document": <full rule>}`. It replaces `field is one of` with `field_in_set@1`, `these fields are empty` with `fields_all_empty@1`, `name tokens match` with `token_match@2`, `name tokens match with any ampersand` with `token_match@1`, `held back` (in a verdict or in `emits`) with `deferred`, and the step key `probable entity type` with `probable_kind`. `otherwise` is the same word and key. A stored key typed bare (`deferred`, `field_in_set@1`, `fields_all_empty@1`, `token_match@1`, `token_match@2`, `probable_kind`) is refused naming the word to type and every word the file accepts. The produced rule goes through `classification.check_rule`, so a rule with no `otherwise` step, an undeclared verdict, or a `probable entity type` on a step that decides an entity type is refused. The file imports nothing from `entity_type.py`; the page lists the words only once that family file exists.

## Comments

