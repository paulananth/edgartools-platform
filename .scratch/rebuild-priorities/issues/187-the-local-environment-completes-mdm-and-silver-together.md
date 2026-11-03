# 187: The local environment completes MDM and silver together

Priority: 187. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 17:27 ET, from the operator: "Fix env pipeline must complete both mdm and silver together" and "Build silver in Postgres server".

Type: task. Status: open. Blocked by: none.

## Question

The shared environment omitted silver by default (its env files unset the silver login), so a source with a silver target could finish its tests in containers while no silver rows ever landed on the shared server, and "complete" meant MDM only. How does the environment make silver part of every run?

## Parts

- [x] Silver database created on the shared server and every committed silver spec registered (2026-11-03 17:27 ET): 13 tables, all empty; 4 older empty tables (company fact, line item, measure, N-PORT holding) replaced by the current specs; `edgar-warehouse silver register` created 8 of 8
- [x] `local-test-stores.py up` includes silver by default (`--no-silver` leaves it out) and the env files carry the silver login (2026-11-03 17:27 ET): `tests/unit/test_local_test_stores.py` passes; CLAUDE.md, AGENTS.md, docs/local-agent-testing.md say so
- [x] A load of a target that lands silver stops at once when an env file has no silver login (2026-11-03 17:40 ET): `tests/unit/test_rules_loading.py::test_a_target_that_lands_silver_stops_at_once_when_an_env_file_has_no_silver_login`; without the check it fails with `DID NOT RAISE RunStopped`
- [ ] Load the silver-target sources into the shared silver store with MDM (13F filings and Securities, ownership, N-PORT, company facts), and a run reports complete only when both finish
- [ ] Learning → skill
