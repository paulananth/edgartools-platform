# A real individual's name in tests and a spec example

Status: open
Type: task
Owner: Claude

Operator, 2026-11-18: "fix the real individual names in tests". Ticket 02 listed three files that held a real individual's
name as a test input. This repository is public: invented examples only.

## Parts

- [x] Search the tests, docs, skills and rules for well-known individuals and for person-name values in owner-name fields and XML or JSON name tags: the only real individual left (beyond the recorded fixture, replaced in the fixture's own PR) was one SEC filer's registry-form name, in three places 2026-11-18 22:14 ET
- [x] Replace it with an invented name of the same shape (surname, first name, initial) in `tests/engine/test_sec_configured_fields.py` (with an invented CIK), `tests/storage_adapters/test_mastering_undecidable.py` and `docs/specs/person/consumer.md` (both forms of the example) 2026-11-18 22:14 ET
- [x] The recorded answers change once for the one test input that carries the name or its CIK: `sec/normalize/sec.submissions.person/valid` and `.../unknown_fields` in `tests/engine/mapper_outcomes.json` failed (`'359a7b9e…' != '986184d1…'`) and were updated; 47 configured-field tests and the undecidable-mastering tests (3, PostgreSQL) pass 2026-11-18 22:14 ET
- [ ] ~~Names of individuals inside filenames of the research inventory `docs/research/heavy-parse-s3-inventory-2026-09-25.jsonl`, and the `.scratch` research notes~~ deferred to its own ticket: a recorded list of real bronze object keys (not a test input), where a filename can carry a person's name; it needs a decision on whether to keep the recording at all
- [ ] Learning → skill: none (the rule is in CLAUDE.md)
