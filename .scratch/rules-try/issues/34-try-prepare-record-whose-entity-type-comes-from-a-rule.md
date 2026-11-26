# Try Prepare a record whose entity type comes from a rule

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/prepare_by_type_rule.py` only. The person pastes a contract that has `classification`, and the policy. The page calls `normalize`. Do not edit `prepare_record.py`. Do not load `company.yaml`.

Invented pass: the row receives the entity type the pasted rule decides.

## Checklist

- [x] `prepare_by_type_rule.py` is the only production file this ticket adds. `tests/unit/test_rules_try_prepare_by_type_rule.py` is new. 2026-11-25 21:56 ET
- [x] The row receives the entity type the pasted rule decides. `tests/unit/test_rules_try_prepare_by_type_rule.py`. 2026-11-25 21:56 ET
- [x] `prepare_record.py` is not edited. 2026-11-25 21:56 ET
- [x] `company.yaml` is not loaded. `tests/unit/test_rules_try_prepare_by_type_rule.py`. 2026-11-25 21:56 ET
- [x] Learning → skill: none. The family is one call to the existing function. 2026-11-25 21:56 ET

## Answer

`prepare_by_type_rule` shows the title "Prepare a record whose entity type comes from a rule" and four inputs: the row as JSON, the source code, the publication as JSON, and the policy as JSON (`kinds` and `automatic_rules`). The rule box holds the contract as JSON, with `classification` (`kind`, `rule_id`, `version`) in its adapter and no `kind` or `kind_field`. Try calls `edgar_warehouse.mdm.adapters.normalize` with that contract and policy and returns the prepared record. Its `kind` is the entity type the pasted rule decides, and `provenance.classification` names the rule id, version and step. A verdict the policy has not switched on, a verdict that decides no entity type, and a row with no record key each return `{"refused": "The record is set aside: <reason>"}`; the first two name the rule, version, step and verdict. A rule the policy does not hold, held at another version, or written for another source returns the engine's refusal. A contract with no `classification` is refused and names the page "Prepare the MDM record". A contract stating a `kind` or `kind_field` beside `classification` is refused, as registration refuses it. No rules file is opened.

## Comments

