# Open the try page

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: none

## What to build

Add the try page and nothing else. This is the only ticket that creates more than one file. Later tickets do not edit these files.

Command: `edgar-warehouse rules try`. Buttons, fixed: Try, Show the full rule, Keep a copy, Store this draft.

The page shows the inputs the family declares, the rule, and the expected output. The title is the title that family declares. A family appears when `bench_families/<name>.py` exists. `<name>_full.py` is used only when that run file also exists. Compare is JSON equality. The result is one JSON object. A refusal is `{"refused":"..."}`. Keep a copy and Store this draft refuse until tickets 02 and 03 replace their files.

Owns: the page module, empty `bench_families/`, `bench_keep.py`, `bench_store.py`.

## Checklist

- [x] The page, the empty family folder, and the two refuse files exist. `tests/unit/test_rules_try.py`. 2026-11-21 22:03 ET
- [x] `rules try` shows inputs, the rule, and the expected output. `tests/unit/test_rules_try.py`. 2026-11-21 22:03 ET
- [x] A family appears only because its file exists. `tests/unit/test_rules_try.py`. 2026-11-21 22:03 ET
- [x] A temp-folder fake family shows its title and input labels. `tests/unit/test_rules_try.py`. 2026-11-21 22:03 ET
- [x] Compare ignores key order. `tests/unit/test_rules_try.py`. 2026-11-21 22:03 ET
- [x] Keep a copy and Store this draft refuse. `tests/unit/test_rules_try.py`. 2026-11-21 22:03 ET
- [x] No engine call, no `rules/` read, and no database. `tests/unit/test_rules_try.py` patches the database connection and the rules-file loader. 2026-11-21 22:03 ET
- [x] Learning → skill: none. The page is filename discovery and four buttons. No new procedure for a skill. 2026-11-21 22:03 ET

## Answer

`edgar-warehouse rules try --family <name>` prints the page for that family file. The page shows the title and input labels the file declares, a rule box, an expected-output box, and the four buttons. A family is present because `bench_families/<name>.py` exists. `<name>_full.py` is loaded only when that family file is there too. Compare is JSON equality, so key order does not matter and list order does. Keep a copy and Store this draft return a refusal and write nothing. The command does not call an engine, read `rules/`, or open a database.

## Comments

