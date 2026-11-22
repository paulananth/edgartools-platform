# Keep a copy of the try

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Replace `bench_keep.py` only. The Keep a copy button writes the case JSON to a path the person confirms. No version, no write under `rules/`, no database.

## Checklist

- [x] `bench_keep.py` is the only production file this ticket replaces. `tests/unit/test_rules_try.py` was updated because it locked the stub refusal. 2026-11-22 07:05 ET
- [x] A confirmed path reloads as the same JSON. `tests/unit/test_rules_try.py`. 2026-11-22 07:05 ET
- [x] An unconfirmed path is not written. `tests/unit/test_rules_try.py`. 2026-11-22 07:05 ET
- [x] Learning → skill: none. Keeping a copy is the button this ticket promised. 2026-11-22 07:05 ET

## Answer

Keep a copy writes the case JSON to the path the person names. The file reloads as the same JSON. No path means the path is not confirmed, and nothing is written. A path under `rules/` is refused, including a differently spelled name of that same folder. A missing folder and a folder path are refused. There is no version and no database.

The try-page test that expected the stub refusal now expects the kept file. `try_page.py` and `bench_store.py` are unchanged. Store this draft still refuses.

## Comments

