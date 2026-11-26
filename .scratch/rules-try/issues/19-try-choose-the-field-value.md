# Try Choose the field value

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/field_value.py` only. The person pastes the kind, subjects, claims, policy, overrides, as-of time, and policy digest. The page calls `select_fields` with those arguments. Do not call `files.policy()`. Do not attach a source record. Do not decide that two masters are the same subject.

Invented pass: the pasted policy ranks the directory first for `address` and the register first for other fields, and the output follows that.

## Checklist

- [x] `field_value.py` is the only production file this ticket adds. `tests/unit/test_rules_try_field_value.py` is new. 2026-11-25 21:55 ET
- [x] Address comes from the directory and the other field comes from the register. `tests/unit/test_rules_try_field_value.py`. 2026-11-25 21:55 ET
- [x] `files.policy()` is not called. `tests/unit/test_rules_try_field_value.py`. 2026-11-25 21:55 ET
- [x] Learning → skill: none. The family is one call to the existing engine. 2026-11-25 21:55 ET

## Answer

`field_value` shows the title "Choose the field value" and six inputs: the entity type (the engine's `kind`), the subjects as a JSON list, the claims as a JSON object, the steward overrides as a JSON list (empty for none), the as-of time with a time zone, and the policy digest. The rule box holds the policy as JSON. Try calls `edgar_warehouse.mdm.survivorship.select_fields` with those values and returns `{"fields": ..., "profiles": ..., "reviews": ...}`. With the invented policy that ranks the directory first for `address` and the register first for the rest, `address` comes from the directory and `name` from the register, and the claim that lost stays under `conflicts`. A policy that is not a JSON object, a missing input, a list, object or time that does not parse, and a paste the engine refuses (an unknown key in the entity type's block, a field rule with no sources, a time with no time zone) each return `{"refused": "..."}`. `files.policy()` is not called, no source record is attached, and no word decides that two masters are one subject.

## Comments

