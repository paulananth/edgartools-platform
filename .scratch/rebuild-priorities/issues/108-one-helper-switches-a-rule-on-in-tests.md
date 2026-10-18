# One test helper switches a matching rule on

Priority: 108, tier 4, housekeeping (numbered after the map was charted). Map: [Rebuild priorities](../map.md).

Type: task (tests). Status: in review (2026-10-18). Blocked by: none.

## Why

Found by the GoF review of ticket 79's switch-on (2026-10-18): four or more test files switch a matching rule on for themselves with the same five lines (copy `files.policy()`, find the rule, append an `automatic_rules` entry with `family: binding`, `verdict: bind`, `activation: deterministic`): `tests/integration/test_nport_link_start.py`, `tests/integration/test_openfigi_security.py`, `tests/integration/test_clean_issuer_lei_rule.py`, and near copies in `test_clean_shared_cik.py` and `test_clean_identifier_binding.py`. Each switch-on in the live policy then edits every one of them, as ticket 79 did.

## Checklist

- [x] `with_rules_on(policy, kind, *rule_ids)` in `tests/mdm/policy_layers.py`; the two tests that switched a rule on in a copy of the live policy (`test_clean_issuer_lei_rule.py`, `test_nport_link_start.py`, both `gleif-issuer-lei`) call it. The others named in Why build a whole invented policy inline, a different job, so they stay; the OpenFIGI test reads the live policy since #1083. Verified: both tests, and the 812 tests of `tests/mdm` and the N-PORT link tests, pass (2026-10-18 13:51 ET)
- [x] Three-axis review (2026-10-18 13:53 ET): Standards found a blank line and a tick without its evidence (fixed); Spec found the OpenFIGI test's header still saying the ISIN rules are switched on there (fixed), and confirmed the helper's entries equal the removed code's; GoF: leave it
- [ ] PR, CI green, merged on green
- [x] Learning → skill: none; a test helper
