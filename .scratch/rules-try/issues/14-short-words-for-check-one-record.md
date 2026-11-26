# Accept short words for Check one record

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/check_record_full.py` only. This file can merge before ticket 13. The page ignores it until `check_record.py` exists.

- is present → `present@1`
- hold the record out → `exception`
- keep off matching → `withhold`
- count the failure → `flag`
- in the pinned code set → `in_reference@1`

## Checklist

- [x] `check_record_full.py` is the only production file this ticket adds. `tests/unit/test_rules_try_check_record_full.py` is new. 2026-11-26 00:45 ET
- [x] The missing-name case written in these words matches ticket 13. `tests/unit/test_rules_try_check_record_full.py`. 2026-11-26 00:45 ET
- [x] The shown block includes the version string the person types. `tests/unit/test_rules_try_check_record_full.py`. 2026-11-26 00:45 ET
- [x] Learning → skill: none. The words are a table the file reads. 2026-11-26 00:45 ET

## Answer

A short rule is a quality block that may use five words where a check's `test` or `on_fail` goes. Show the full rule returns `{"lines": [...], "document": {...}}`: the words the rule used, each with its stored key, and the same block with every word replaced. `version`, the ids, the paths and the arguments stay as typed. A stored key from the list typed bare (`present@1`, `exception`, `withhold`, `flag`, `in_reference@1`) is refused with the word to type and every word the file accepts. The block is checked with `quality.check_quality`, so a block the quality engine refuses returns `{"refused": "..."}`. No `rules/reference` file is read; "in the pinned code set" only writes `in_reference@1`.

## Comments

