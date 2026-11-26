# Accept short words for Summarize every row

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/whole_set_full.py` only. Accept only: how many rows, distinct values, most frequent. Refuse "how many at this path". This file can merge before ticket 10. The page ignores it until `whole_set.py` exists.

## Checklist

- [x] `whole_set_full.py` is the only production file this ticket adds. `tests/unit/test_rules_try_whole_set_full.py` is new. 2026-11-25 21:55 ET
- [x] The three-row case written in those words matches ticket 10. `tests/unit/test_rules_try_whole_set_full.py` runs the shown plan through `ReductionEngine` and checks ticket 10's count, distinct values and most-frequent value, since `whole_set.py` is not on this branch. 2026-11-25 21:55 ET
- [x] "how many at this path" is refused. `tests/unit/test_rules_try_whole_set_full.py`. 2026-11-25 21:55 ET
- [x] Learning → skill: none. The file is a word table over the existing plan. 2026-11-25 21:55 ET

## Answer

`whole_set_full.py` declares `words` and `explain(rule)`. Show the full rule takes a short rule, a document with a `reduce` block, and replaces each group's `mode` word by its stored mode: "how many rows" is `count`, "distinct values" is `members`, "most frequent" is `most`. It returns `{"lines": [...], "document": {...}}`, the words used beside their stored modes and the full document, after `ReductionEngine` accepts the plan. The bounds and the group columns stay as pasted. A stored mode typed bare (`count`, `members`, `most`) is refused with the word to type; "how many at this path" is refused as a read-file check, not a summary of rows; any other mode is refused. Each refusal lists the three words this file accepts. A short rule that is not JSON, has no reduce block, or that the engine refuses returns `{"refused": "..."}`.

## Comments

