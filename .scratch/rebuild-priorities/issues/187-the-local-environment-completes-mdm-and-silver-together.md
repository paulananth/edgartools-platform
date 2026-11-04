# 187: The local environment completes MDM and silver together

Priority: 187. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 17:27 ET, from the operator: "Fix env pipeline must complete both mdm and silver together" and "Build silver in Postgres server".

Type: task. Status: resolved. Blocked by: none.

## Question

The shared environment omitted silver by default (its env files unset the silver login), so a source with a silver target could finish its tests in containers while no silver rows ever landed on the shared server, and "complete" meant MDM only. How does the environment make silver part of every run?

## Parts

- [x] Silver database created on the shared server and every committed silver spec registered (2026-11-03 17:27 ET): 13 tables, all empty; 4 older empty tables (company fact, line item, measure, N-PORT holding) replaced by the current specs; `edgar-warehouse silver register` created 8 of 8
- [x] `local-test-stores.py up` includes silver by default (`--no-silver` leaves it out) and the env files carry the silver login (2026-11-03 17:27 ET): `tests/unit/test_local_test_stores.py` passes; CLAUDE.md, AGENTS.md, docs/local-agent-testing.md say so
- [x] A load of a target that lands silver stops at once when an env file has no silver login (2026-11-03 17:40 ET): `tests/unit/test_rules_loading.py::test_a_target_that_lands_silver_stops_at_once_when_an_env_file_has_no_silver_login`; without the check it fails with `DID NOT RAISE RunStopped`
- [x] (2026-11-03 20:13 ET) Manager filings (`sec.thirteenf.filings`, silver) loaded into the shared silver store: 144 of 149 bundles complete, 323,217 rows with 323,217 distinct keys (no duplicates), 8,309 managers, filing dates 1996-02-14 to 2026-09-11; 118 managers have a `manager_mdm_id` (the local MDM masters few Companies). A first load failed on 8 bundles (a filing listed by two managers broke the one-row-per-filing key), so the key is accession number and manager (`tests/integration/test_thirteenf_filing_silver.py`, fails on the old key); 45 min for the main load
  - [ ] ~~The last 5 of 149 bundles (about 3% of documents; they stopped at the landing step on the 45-minute limit)~~ deferred (operator, 2026-11-03 20:13 ET: "ship the code"): rerun the same `load` command to finish them; until then no filing listed by two managers is in silver, so the new key is proven by its test, not yet by the data
  - [ ] ~~Ownership, N-PORT and company facts loaded into the shared silver store~~ deferred: each has its own ticket and load (N-PORT holdings: ticket 79)
- [x] (2026-11-03 20:13 ET) Learning → skill: `skills/data-operations/SKILL.md` (a source that masters nothing needs no proof, and a silver-only load stops at once without a silver login)
