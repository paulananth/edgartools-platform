# Accept short words for Attach a source record

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/attach_record_full.py` only. A word for combining two existing masters is refused. That decision stays on `rules test`. "attach" here is this family only. Ticket 08's "attach" means grouped rows. The page title tells them apart, and each file refuses the other family's words.

This file can merge before ticket 22. The page ignores it until `attach_record.py` exists.

- same identifier → `identifier_match@1`
- how many that identifier allows → `identifier_cardinality@1`
- attach → `bind`
- create a master → `mint`
- send to review → the review outcome

## Checklist

- [x] `attach_record_full.py` is the only production file this ticket adds. `tests/unit/test_rules_try_attach_record_full.py` is new. 2026-11-26 00:20 ET
- [x] The one-master and two-master cases written in these words match ticket 22. `tests/unit/test_rules_try_attach_record_full.py`. 2026-11-26 00:20 ET
- [x] A word for combining two existing masters is refused. `tests/unit/test_rules_try_attach_record_full.py`. 2026-11-26 00:20 ET
- [x] Learning → skill: none. The file is a table of words over the engine's own policy keys. 2026-11-26 00:20 ET

## Answer

`attach_record_full.py` lists five words: same identifier (`identifier_match@1`), how many that identifier allows (`identifier_cardinality@1`), attach (`bind`), create a master (`mint`) and send to review (`review`). Show the full rule takes a short policy and returns `{"lines": [...], "document": ...}`: the policy with each word replaced by its stored key, and one line for each word used. The words work in `when` (`primitive`), `emits`, `verdict` of `automatic_rules`, `on_no_match`, `on_several` and `on_conflict`; the plain keys `wait`, `review` and `first`, and other record tests, stay as typed. A bare `bind`, `mint`, `identifier_match@1` or `identifier_cardinality@1` is refused with `Type '<word>' instead.` and the accepted words. A word for combining two existing masters (`merge`, `combine the masters`, `consolidate`, `same subject` and the like), as a key or a value anywhere, is refused and sends the person to `rules test`. The words of Group and attach rows (ticket 08) and Read the file are refused naming their family; "attach" here is binding a source record, and ticket 08's "attach" (stored `joins`) is a different word on a different page. A policy the engine's `plan_record_matches` refuses on an empty batch is refused with the engine's text. The one-master, two-master and no-master cases written in these words, run on the Attach a source record page, return attach, send to review and create a master.

## Comments

