# Move the primitive catalog out of the primer

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01, 37

## What to build

Add `docs/engine-rules-reference.md`. Edit the primer only to remove the catalog this ticket is moving, and leave a pointer where the catalog was. Add one file-only test that every named primitive exists. Do not edit a family file or the shell.

This ticket waits for 37 because both edit the primer.

## Checklist

- [x] The catalog lives in `docs/engine-rules-reference.md`. The catalog is the source-expression primitives: the three tables of the primer's sections 2, 4 and 5, unchanged. 2026-11-26 00:31 ET
- [x] The primer points at that file where the catalog was: in sections 2, 4 and 5, each to its table. 2026-11-26 00:31 ET
- [x] A file-only test checks that every named primitive exists. `tests/unit/test_engine_rules_reference.py` reads the reference's tables and `crates/source-contract/src/lib.rs`; adding a row for a name the evaluator does not read fails it. 2026-11-26 00:31 ET
- [x] No family file and no shell file is edited. 2026-11-26 00:31 ET
- [x] Learning → skill: none. The reference is a document and a file check. 2026-11-26 00:31 ET

## Answer

`docs/engine-rules-reference.md` holds the source-expression primitives in three tables (values, conditions, lookups), moved from the primer's sections 2, 4 and 5 with their rows unchanged. The primer keeps the prose, the examples, the text-transform vocabulary, the source-check names, and the MDM quality and policy primitives, and links to the reference where each table stood. `tests/unit/test_engine_rules_reference.py` fails when a name in the reference's tables is not a quoted name in the evaluator's source.

## Comments
