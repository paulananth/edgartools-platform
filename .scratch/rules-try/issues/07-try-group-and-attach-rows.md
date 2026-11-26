# Try Group and attach rows

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/group_rows.py` only. The person pastes the plan and the input tables. The page calls `combine_tables`. Do not import `read_file.py`.

Invented pass: row `R1` with names `B` then `A` produces aliases `["A","B"]`.

## Checklist

- [x] `group_rows.py` is the only production file this ticket adds. `tests/unit/test_rules_try_group_rows.py` is new. 2026-11-25 21:53 ET
- [x] The R1 alias case matches `["A","B"]`. `tests/unit/test_rules_try_group_rows.py`. 2026-11-25 21:53 ET
- [x] This file does not import `read_file.py`. 2026-11-25 21:53 ET
- [x] Learning → skill: none. The family is one call to the existing combination. 2026-11-25 21:53 ET

## Answer

`group_rows` shows the title "Group and attach rows" and one input: the input tables as JSON (a reading name, a table name, and that table's rows). The rule box holds the combination contract as JSON, in the primer's section 6 shape: `execution` with the profile `source.combine`, and `combine` with `max_rows`, `groups` and `tables`. Try checks the contract with the combine worker's own contract check (`edgar_warehouse.workers.source_combine._contract`, since `combine_tables` does not validate its plan and accepts an unknown group mode), refuses more rows than `max_rows`, then calls `edgar_warehouse.rules.source_engine.combine_tables` with `edgar_warehouse.control_contract.canonical`, the equality the combine worker passes. It returns `{"tables": ...}`. Row `R1` with names `B` then `A` returns `{"tables": {"records": [{"id": "R1", "aliases": ["A", "B"]}]}}`. A rule that is not a JSON object, a contract the check refuses, tables that are not JSON or not tables of rows, a missing reading, a key that is not text, an integer or null, and a group that must hold one row but holds two each return `{"refused": "..."}`.

## Comments
