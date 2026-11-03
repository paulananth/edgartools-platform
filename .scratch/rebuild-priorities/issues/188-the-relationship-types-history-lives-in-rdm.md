# 188: The relationship types' history lives in RDM, not in a test fixture

Priority: 188. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 17:46 ET, from the operator: "This must be part of rdm" (about `tests/mdm/fixtures/relationship-types-v1.yaml`).

Type: task. Status: open. Blocked by: [182](182-the-other-capacity-of-a-reporting-owner.md) (it adds version 2 of the code set).

## Question

Ticket 132 moved the relationship types into the RDM code set `mdm-relationship-types` ("Use RDM for keeping types and other information"). A test still keeps an older table of the same types in `tests/mdm/fixtures/relationship-types-v1.yaml`, which the test layer `without_real_names` (`tests/mdm/policy_layers.py`) uses to rebuild the policy the operator approved before the types had their real names, and `tests/mdm/test_clean_relationship_types.py` keeps a second copy as `BEFORE`. That is two more copies of one vocabulary outside RDM. How do the earlier tables become versions of the one code set?

## Parts

- [ ] List every copy of the relationship types outside RDM (the fixture, `BEFORE`, the layers in `policy_layers.py` that edit `types`) and what each one proves
- [ ] Publish each earlier table as a version of `mdm-relationship-types` in `rules/reference/published/`, so the layers read their types from RDM by version
- [ ] Delete the fixture and `BEFORE`; the approval-history digests (`tests/mdm/test_rules_config_digests.py`) stay unchanged
- [ ] Learning → skill
