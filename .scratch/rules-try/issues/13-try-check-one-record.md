# Try Check one record

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/check_record.py` only. The person pastes the quality block, the fields, and the matching input. The page calls `quality.apply`. A held-out record is `{"held out":"quality_<id>"}`, and the page shows the stored word `exception` beside "held out".

Invented pass: a present name passes. A missing name written as "is present" and "hold the record out" is held out.

Known leftover: if the paste itself uses `in_reference@1` or `in_hierarchy@1`, `apply` already reads `rules/reference`. This ticket does not add another read. The test uses "is present" only.

## Checklist

- [x] `check_record.py` is the only production file this ticket adds. `tests/unit/test_rules_try_check_record.py` is new. 2026-11-25 21:53 ET
- [x] An invented present name passes. `tests/unit/test_rules_try_check_record.py`. 2026-11-25 21:53 ET
- [x] A missing name is held out, with `exception` shown beside "held out". `tests/unit/test_rules_try_check_record.py`. 2026-11-25 21:53 ET
- [x] The test does not use an in-reference check. `tests/unit/test_rules_try_check_record.py`. 2026-11-25 21:53 ET
- [x] Learning → skill: none. The family is one call to the existing quality engine. 2026-11-25 21:53 ET

## Answer

`check_record` shows the title "Check one record" and two inputs: the record's fields as a JSON object and the matching input as a JSON object (empty for none). The rule box holds the quality block as JSON. Try checks the block with `quality.check_quality`, then calls `edgar_warehouse.mdm.quality.apply` and returns its `provenance.quality` (`version`, and per check `kind`, `failure_action`, `rows_checked`, `rows_failed`, with `fixes`, `withheld` and `flags` when they apply). A failed `exception` check returns `{"held out": "quality_<id>", "on_fail": "exception"}`, so `exception` sits beside "held out". A rule or input that is not a JSON object, and a block the quality engine refuses (an unknown test, a missing version, a bad `on_fail` or path), each return `{"refused": "..."}`. The try adds no read of `rules/reference`; a block that uses `in_reference@1` or `in_hierarchy@1` reads it inside `apply`, as `apply` already does.

## Comments

