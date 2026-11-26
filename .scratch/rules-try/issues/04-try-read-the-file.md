# Try Read the file

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/read_file.py` only. The person pastes a read document, the file bytes, and any lookup lists. The page calls `SourceEngine.read`. Do not open a capture folder.

Invented pass: `{"records":[{"id":"R1","name":"  Example Works  ","quantity":"12"}]}` becomes one row `{"id":"R1","name":"Example Works","quantity":12}`. A bad paste returns `{"refused":"..."}`.

## Checklist

- [x] `read_file.py` is the only production file this ticket adds. `tests/unit/test_rules_try_read_file.py` is new, and `tests/unit/test_rules_try.py` changed because it locked the empty family folder. 2026-11-25 21:42 ET
- [x] The invented R1 row matches the expected output. `tests/unit/test_rules_try_read_file.py`. 2026-11-25 21:42 ET
- [x] A bad paste is a refusal object, not a traceback on the page. `tests/unit/test_rules_try_read_file.py`. 2026-11-25 21:42 ET
- [x] No capture folder is opened. `tests/unit/test_rules_try_read_file.py`. 2026-11-25 21:42 ET
- [x] Learning → skill: none. The family is one call to the existing engine. 2026-11-25 21:42 ET

## Answer

`read_file` shows the title "Read the file" and two inputs: the file as text and the lookup lists as JSON. The rule box holds the read document as JSON. Try calls `edgar_warehouse.rules.source_engine.SourceEngine.read` and returns `{"tables": ..., "deferred": ...}`. A rule that is not a JSON object, a read document the engine refuses, a file the read refuses, and lookup lists that are not a JSON object of lists of texts each return `{"refused": "..."}`. No folder is opened and no `rules/` file is read.

## Comments
