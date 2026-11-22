# Try Choose the field value

Type: task
Status: open
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/field_value.py` only. The person pastes the kind, subjects, claims, policy, overrides, as-of time, and policy digest. The page calls `select_fields` with those arguments. Do not call `files.policy()`. Do not attach a source record. Do not decide that two masters are the same subject.

Invented pass: the pasted policy ranks the directory first for `address` and the register first for other fields, and the output follows that.

## Checklist

- [ ] `field_value.py` is the only file this ticket adds
- [ ] Address comes from the directory and the other field comes from the register
- [ ] `files.policy()` is not called
- [ ] Learning → skill

## Comments

