# 163: Master tables carry their identifier checks in the catalog

Priority: 163. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 06:45 ET (operator, 2026-11-02: "why there are no data quality checks and mapping in open metadata", then "login again and fix in order").

Type: task. Status: resolved. Blocked by: none.

## Question

The catalog holds 29 quality cases on source and silver tables and none on the master kind tables, where checks matter most. Which checks do the kind rules already state, and how does the catalog show them?

Answer: each kind file states, for every identifier, how many values one master may hold (`claim.forward`) and how many masters one value may name (`claim.reverse`). Those limits are the master checks. No check is invented.

## Parts

- [x] GoF consult on `_quality` before the code: leave it, add one function of the same shape (2026-11-02 06:46 ET)
- [x] The publisher adds one case per identifier limit on the kind table: 17 cases on 4 kinds (`tests/unit/test_rules_catalog.py::test_each_identifier_limit_of_a_kind_is_a_check_on_its_master_table`, 36 pass, 2026-11-02 06:46 ET)
- [x] `rules catalog check` matches after a publish; live count 46 cases (29 + 17) (2026-11-02 06:46 ET)
- [ ] ~~The 46 cases have no result~~ deferred to 165: the results come from the engine's own check runs
- [x] Learning → skill: `skills/openmetadata/SKILL.md` names where master checks come from (2026-11-02 06:46 ET)
