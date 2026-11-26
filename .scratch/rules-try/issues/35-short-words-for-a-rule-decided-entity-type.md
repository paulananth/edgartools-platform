# Accept short words for a rule-decided entity type

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/prepare_by_type_rule_full.py` only. Same words as ticket 32, plus "entity type rule" → `classification`. This is the only file that accepts "entity type rule". This file can merge before ticket 34. The page ignores it until `prepare_by_type_rule.py` exists.

## Checklist

- [x] `prepare_by_type_rule_full.py` is the only production file this ticket adds. `tests/unit/test_rules_try_prepare_by_type_rule_full.py` is new. 2026-11-26 01:12 ET
- [x] The rule-decided case written with "entity type rule" matches ticket 34. `tests/unit/test_rules_try_prepare_by_type_rule_full.py`. 2026-11-26 01:12 ET
- [x] No other full-rule file accepts "entity type rule". `tests/unit/test_rules_try_prepare_by_type_rule_full.py` lists the words of every family in the folder. 2026-11-26 01:12 ET
- [x] Learning → skill: none. The words are a table the file reads. 2026-11-26 01:12 ET

## Answer

A short rule is a contract whose `adapter` may use five words where a stored key goes: "entity type" → `kind`, "record key" → `record_key`, "identifier" → `identifiers`, "lookup only" → `cross_references`, and "entity type rule" → `classification`. Inside the entity type rule, "entity type" is the `kind` that names the policy's block holding the rule; `rule_id` and `version` keep their names. Show the full rule returns `{"lines": [...], "document": {...}}`: the words the rule used with their stored keys, and the contract with every word replaced; the document is the one Try takes on the "Prepare a record whose entity type comes from a rule" page. A stored key from the list typed bare, at the adapter or inside the rule, is refused with the word to type and every word the file accepts. A contract that uses both "entity type" and "entity type rule" is refused ("not both"). A paste that is not JSON or has no `adapter` block is refused.

## Comments

