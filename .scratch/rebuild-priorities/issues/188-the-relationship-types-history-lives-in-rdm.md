# 188: The relationship types' history lives in RDM, not in a test fixture

Priority: 188. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 17:46 ET, from the operator: "This must be part of rdm" (about `tests/mdm/fixtures/relationship-types-v1.yaml`).

Type: task. Status: resolved. Blocked by: [182](182-the-other-capacity-of-a-reporting-owner.md) (it adds version 2 of the code set).

## Question

Ticket 132 moved the relationship types into the RDM code set `mdm-relationship-types` ("Use RDM for keeping types and other information"). A test still keeps an older table of the same types in `tests/mdm/fixtures/relationship-types-v1.yaml`, which the test layer `without_real_names` (`tests/mdm/policy_layers.py`) uses to rebuild the policy the operator approved before the types had their real names, and `tests/mdm/test_clean_relationship_types.py` keeps a second copy as `BEFORE`. That is two more copies of one vocabulary outside RDM. How do the earlier tables become versions of the one code set?

## Parts

- [x] (2026-11-03 19:31 ET) List every copy of the relationship types outside RDM (the fixture, `BEFORE`, the layers in `policy_layers.py` that edit `types`) and what each one proves: two copies, the fixture (rebuilds the pre-real-names policy) and `BEFORE` (proves version 2 adds only the other capacity); the other layers edit the policy, not a table
- [x] (2026-11-03 19:31 ET) Publish each earlier table as a version of `mdm-relationship-types` in `rules/reference/published/`, so the layers read their types from RDM by version: code set `mdm-relationship-types-before-real-names` v1 (23 rows), read by `without_real_names`; 145 passed
- [x] (2026-11-03 19:31 ET) Delete the fixture and `BEFORE`; the approval-history digests (`tests/mdm/test_rules_config_digests.py`) stay unchanged: `tests/mdm/test_rules_config_digests.py` + `test_clean_relationship_types.py` 145 passed; `BEFORE` replaced by `test_version_2_of_the_code_set_adds_only_the_other_capacity`
- [x] (2026-11-03 17:47 ET) Learning → skill, written first on the operator's instruction: `skills/data-modeling/SKILL.md`, "Types and reference data live in RDM, never in files"
- [x] (2026-11-03 19:31 ET) Learning → skill: none beyond part 4; the earlier table is its own code set because versions 1 and 2 of the live set are pinned by the approval-history digests, and a version needs a supersedes chain
