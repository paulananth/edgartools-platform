# Accept short words for Group and attach rows

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/group_rows_full.py` only. "how many at this path" is refused here. That phrase belongs to ticket 05. This file can merge before ticket 07. The page ignores it until `group_rows.py` exists.

- list the values → `collect`
- one flat list → `collect_flat`
- first row, last row → `first`, `last`
- exactly one row → `one`
- how many rows → `count` on a reduction
- distinct values → `members`
- most frequent → `most` (blank when two tie)
- attach → `joins` (grouped rows, not a source record)

## Checklist

- [x] `group_rows_full.py` is the only production file this ticket adds. `tests/unit/test_rules_try_group_rows_full.py` is new. 2026-11-25 21:56 ET
- [x] The R1 case written with "list the values" and "attach" matches ticket 07. `tests/unit/test_rules_try_group_rows_full.py` runs the shown document through `combine_tables` and gets `["A","B"]`. 2026-11-25 21:56 ET
- [x] "how many at this path" is refused. `tests/unit/test_rules_try_group_rows_full.py`. 2026-11-25 21:56 ET
- [x] Learning → skill: none. The words are a table the file reads. 2026-11-25 21:56 ET

## Answer

A short rule is a combination contract (a `combine` block) or a reduction contract (a `reduce` block) that may use the words in the list where a stored key goes. Show the full rule returns `{"lines": [...], "document": {...}}`: the words the rule used, each with its stored key, and the same document with every word replaced. Group-mode words are replaced in a group's `mode` (the five row words in a `combine` block, the three whole-set words in a `reduce` block); "attach" replaces the table key that holds the joins with `joins`. A mode word of the other kind of block is refused. A stored key from the list typed bare, such as `collect`, `one` or `joins`, is refused with the word to type. "how many at this path" is not a word: it is refused and names Read the file. The words of Attach a source record ("same identifier", "how many that identifier allows", "create a master", "send to review") are refused and name that family; "attach" here is grouped rows joined to a row, never a source record bound. Every refusal lists the words this file accepts. The produced document is checked by the combine worker's contract check (`edgar_warehouse.workers.source_combine._contract`) for a combination, and by the native `ReductionEngine` for a reduction, so a document the engine refuses is refused. A paste that is not JSON, not one object, with both blocks or neither, comes back as `{"refused": "..."}`.

## Comments
