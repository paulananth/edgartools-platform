# Try Prepare the MDM record

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/prepare_record.py` only. The person pastes a contract with a fixed entity type and no classification key. The page calls `normalize`. A contract that contains `classification` is refused before `normalize` runs. The word on the page for `kind` is entity type.

Invented pass: one row, a fixed entity type, and one identifier come back as that entity type, that record key, and that identifier. A row missing the key returns the engine's refusal.

## Checklist

- [x] `prepare_record.py` is the only production file this ticket adds. `tests/unit/test_rules_try_prepare_record.py` is new. 2026-11-25 21:54 ET
- [x] The fixed-type row produces that entity type, record key, and identifier. `tests/unit/test_rules_try_prepare_record.py`. 2026-11-25 21:54 ET
- [x] A missing key is refused. `tests/unit/test_rules_try_prepare_record.py`. 2026-11-25 21:54 ET
- [x] A contract that contains classification is refused before `normalize`. `tests/unit/test_rules_try_prepare_record.py`. 2026-11-25 21:54 ET
- [x] Learning → skill: none. The family is one call to the existing function. 2026-11-25 21:54 ET

## Answer

`prepare_record` shows the title "Prepare the MDM record" and three inputs: the row as JSON, the source code, and the publication as JSON (`publication_key`, `revision`, `artifact_sha256`, `member`). The rule box holds the contract as JSON. Try calls `edgar_warehouse.mdm.adapters.normalize` and returns the prepared record it returns. A fixed-type row comes back with the contract's `kind` (the entity type), the record key and the identifiers the contract maps. A contract that contains `classification`, at the top or in `adapter`, is refused before `normalize` runs, and the refusal names the page "Prepare a record whose entity type comes from a rule". A row the engine sets aside, such as one with no record key, returns `{"refused": "The record is set aside: missing_record_identity"}`. A contract or publication that is not JSON, has no adapter, or lacks a part `normalize` reads returns `{"refused": "..."}`. No traceback reaches the page.

## Comments

