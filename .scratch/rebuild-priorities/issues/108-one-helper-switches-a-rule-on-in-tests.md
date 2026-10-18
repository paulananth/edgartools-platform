# One test helper switches a matching rule on

Priority: 108, tier 4, housekeeping (numbered after the map was charted). Map: [Rebuild priorities](../map.md).

Type: task (tests). Status: open. Blocked by: none.

## Why

Found by the GoF review of ticket 79's switch-on (2026-10-18): four or more test files switch a matching rule on for themselves with the same five lines (copy `files.policy()`, find the rule, append an `automatic_rules` entry with `family: binding`, `verdict: bind`, `activation: deterministic`): `tests/integration/test_nport_link_start.py`, `tests/integration/test_openfigi_security.py`, `tests/integration/test_clean_issuer_lei_rule.py`, and near copies in `test_clean_shared_cik.py` and `test_clean_identifier_binding.py`. Each switch-on in the live policy then edits every one of them, as ticket 79 did.

## Checklist

- [ ] `with_rules_on(policy, kind, rule_ids)` in `tests/mdm/policy_layers.py`; each test that switches a rule on locally calls it
- [ ] The affected tests pass; PR, CI green, merged on green
- [ ] Learning → skill
