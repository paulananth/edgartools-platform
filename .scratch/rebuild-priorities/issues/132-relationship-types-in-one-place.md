# 132: Relationship types in one place

Priority: 132, tier 2. Map: [Rebuild priorities](../map.md). Opened 2026-10-22
from a lean review of how MDM masters relationships (operator: "Is this
following lean principles especially not incurring 7 wastes", then "Fix 1").

**Waste:** overprocessing. The relationship types MDM masters are written
twice: `rules/merge/relationships.yaml` (carried in the Mastering Policy) and a
code copy, `TYPES_V0` in `edgar_warehouse/mdm/clean/relationships.py`, kept
for a policy registered before the types became data. The YAML's own comment
says "the two must agree", and a test holds them equal. The default
ultimate-parent type `CALCULATED_V0` is the same kind of leftover. The rebuild
keeps no legacy behaviour (operator, 2026-09-26).

**What to build:** the types come only from the policy. A policy with no
`relationships` section is refused by name, never mastered with a code table;
an ultimate parent's type comes only from its hierarchy's `ultimate_type`.

**Blocked by:** Codex PR #1121. It rewrites `relationships.py` (the folding
moves into the source engine) and keeps the duplicate as
`CATALOG["legacy_relationships"]`; this ticket removes it from #1121's version,
so the two never conflict (as fix 2 of ticket 129: "Wait for #1121").

**Status:** open, unblocked (2026-10-22 21:11 ET): #1121 merged (2026-10-22 19:08 ET); build on its version of `relationships.py`

- [ ] Check that no registered policy a run can still use lacks the `relationships` section (the active policy, and any policy a replay reads)
- [ ] `TYPES_V0` / `CATALOG["legacy_relationships"]` and `CALCULATED_V0` / `legacy_ultimate_type` removed; `types_of` refuses a policy with no relationship types
- [ ] Every hierarchy with `ultimate_parent` names its `ultimate_type` in `rules/merge/relationships.yaml` (registration refuses one that does not)
- [ ] Tests: `tests/mdm/test_clean_relationship_types.py` and `tests/mdm/policy_layers.py` read the YAML only; a policy without the section is refused
- [ ] The comment in `rules/merge/relationships.yaml` that names the code copy removed
- [ ] PR merged
- [ ] Learning → skill
