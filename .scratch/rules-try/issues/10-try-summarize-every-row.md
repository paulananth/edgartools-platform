# Try Summarize every row

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/whole_set.py` only. The person pastes the reduce plan and the rows. The page calls the existing reduce finish. Do not import `group_rows.py`.

Invented pass: three rows, two of them the same member, produce that count, those distinct values, and that most-frequent value. A two-way tie produces a blank for most frequent.

## Checklist

- [x] `whole_set.py` is the only production file this ticket adds. `tests/unit/test_rules_try_whole_set.py` is new. 2026-11-25 21:53 ET
- [x] The three-row case matches the count, the distinct values, and the most-frequent value. `tests/unit/test_rules_try_whole_set.py`. 2026-11-25 21:53 ET
- [x] A two-way tie is blank. `tests/unit/test_rules_try_whole_set.py`. 2026-11-25 21:53 ET
- [x] This file does not import `group_rows.py`. `tests/unit/test_rules_try_whole_set.py`. 2026-11-25 21:53 ET
- [x] Learning → skill: none. The family is one call to the existing engine. 2026-11-25 21:53 ET

## Answer

`whole_set` shows the title "Summarize every row" and one input: the rows, as JSON, a group name from the plan and that group's rows. The rule box holds a document with a `reduce` block as JSON. Try builds `edgar_warehouse.rules.source_engine.ReductionEngine` from the block, pushes each group's rows, and calls `ReductionEngine.finish`; it returns `{"groups": {...}}` with one row per key, in key order, for each group in the plan. Mode `count` gives how many rows, `members` gives how many distinct values and lists them, and `most` gives the most frequent value. The three invented rows Alpha, Beta, Alpha under key K1 give a count of 3, two distinct values (Alpha, Beta), and the most frequent value Alpha filed twice. Alpha and Beta once each give `null`, shown as blank, for the most frequent value. A rule that is not a JSON object with a reduce block, a plan the engine refuses, rows that are not JSON or not a JSON object of lists, a row the engine refuses (a key that is not text, a missing value), an unknown group and a budget the rows exceed each return `{"refused": "..."}`. No database or folder is opened.

## Comments

