# 171: The Dataset Contracts section is not named `mdm`

Priority: 171. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 09:38 ET (operator, 2026-11-02: "Reading rules can not be named reading[\"mdm\"]"; chosen name: `dataset_contracts`, "dataset_contracts (Recommended)").

Type: task. Status: resolved. Blocked by: none (169 slice 1 merged).

## Question

Each source's rules file (`rules/sources/<source>/source.yaml`) has a top-level `mdm:` section. It holds that source's Dataset Contracts (what its records are, for master data). It is not the MDM database, and a source that writes nothing to master data (company facts) has none. The code reads it as `reading["mdm"]`, which reads as the MDM database. What is it called?

Answer: `dataset_contracts` (the CONTEXT.md term). Measured: 10 rules files, 23 Python uses in `edgar_warehouse`, 41 test lines, nothing in Rust.

## Parts

- [x] GoF consult before any code (2026-11-02 10:24 ET): a rename; leave the structure, rename the key and keep one reader per place
- [x] List every use first (2026-11-02 10:24 ET): 10 rules files, 20 Python lines in `edgar_warehouse`, 1 skill script, the Rules database trigger (Postgres migrations and the MySQL payload) and 19 test files; unrelated and kept: the MDM database and schema, bookkeeping targets and leases named `mdm`, the journal producer `mdm`, the `mdm` command, run-result dictionaries; and: `rg` for `["mdm"]`, `.get("mdm")`, `mdm:` in the rules files, docs and skills; separate the section key from the unrelated words (MDM database, `mdm.prepare` and `mdm.merge` operations, `MDM_DATABASE_URL`, the `mdm` catalog database), which keep their names
- [x] Rename the key in the 10 rules files and every reader (2026-11-02 10:24 ET); an old key is refused by `files.load_source` with a message naming the new one. The Rules database approval trigger tests the new key: new migration `005_dataset_contracts_key.sql` (Postgres) and the MySQL payload and every reader, the validators and mapping documents; an old key is refused with a message naming the new one (no silent fallback)
- [x] Mapping Documents: none change (`test_rules_mapdoc.py` passes on the committed workbooks, 2026-11-02 10:24 ET); the rules digests change because the key name is part of the digested body
- [x] Tests (2026-11-02 10:24 ET): `tests/unit` and `tests/mdm` (all pass), the Postgres integration tests that build a rules document (configured bookkeeping, approval, proving, declared chain) and the MySQL rules runtime adapter test pass; `test_a_rules_file_with_the_old_mdm_key_is_refused` added (rules, target manifest, change journal, mapdoc, catalog, sequence); one test that a file with the old key is refused
- [x] The bookkeeping, data-catalog, data-platform and data-onboarding skills say `dataset_contracts` (2026-11-02 10:24 ET), data-onboarding and refining-rules skills and the docs say `dataset_contracts`
- [x] Learning → skill (2026-11-03 12:39 ET): done with the rename (the bookkeeping, data-catalog, data-platform and data-onboarding skills say `dataset_contracts`); a search of skills, docs, CONTEXT.md, AGENTS.md and CLAUDE.md for `reading["mdm"]`, `.get("mdm")` and a top-level `mdm:` finds none left

## Review (2026-11-02 10:31 ET)

Three-axis review. Applied: the readers the first search missed because it matched double quotes only (two engine test files and the qualification scripts); the data-onboarding template and the README row; a Rules-database refusal of an old-key source version (saved, proven or activated; retiring one stays possible) in the Postgres migration and the MySQL payload, with a test; a test that an old-key file is refused. Left: `.scratch` trial scripts are records of past runs, not run by CI; `docs/specs/source-contract/spec.md` line 982 is an expected-outcome key, not the rules section; GoF: leave the 12 readers (an accessor saves nothing until the next rename).

**Digests.** Every source's rules digest changes with the key name. A proof, approval or MDM handoff receipt pinned to an old digest no longer matches, so a source version already active in a Rules database is saved, proved and approved again. This machine has no Rules database login, and the rebuild is the only system (operator, 2026-09-26), so no live version is lost; a hosted database is migrated by re-saving its sources. The mapping workbooks do not change.
