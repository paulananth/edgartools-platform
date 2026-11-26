# Accept short words for Prepare the MDM record

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/prepare_record_full.py` only. "entity type rule" is refused here. Ticket 35 is the only file that accepts it. This file can merge before ticket 31. The page ignores it until `prepare_record.py` exists.

- entity type → `kind`
- record key → the adapter's record key
- identifier → the adapter's identifier list
- lookup only → a cross-reference that does not match by itself

## Checklist

- [x] `prepare_record_full.py` is the only production file this ticket adds. `tests/unit/test_rules_try_prepare_record_full.py` is new. 2026-11-26 01:40 ET
- [x] The fixed-type case written in these words matches ticket 31. `tests/unit/test_rules_try_prepare_record_full.py`. 2026-11-26 01:40 ET
- [x] "entity type rule" is refused. `tests/unit/test_rules_try_prepare_record_full.py`. 2026-11-26 01:40 ET
- [x] Learning → skill: none. The words are a table the file reads. 2026-11-26 01:40 ET

## Answer

A short rule is a contract whose `adapter` may use four words where a stored key goes: "entity type" → `kind`, "record key" → `record_key`, "identifier" → `identifiers`, "lookup only" → `cross_references` (kept for lookup, never matched by itself). Show the full rule returns `{"lines": [...], "document": {...}}`: the words the rule used, each with its stored key, and the same contract with every word replaced; the document is the one Try takes on the "Prepare the MDM record" page. A stored key from the list typed bare is refused with the word to type and every word the file accepts. "entity type rule" and the stored key `classification` are refused here, in `adapter` or at the top, and the refusal names the page "Prepare a record whose entity type comes from a rule", the one page that accepts "entity type rule". A paste that is not JSON or has no `adapter` block is refused.

## Comments

