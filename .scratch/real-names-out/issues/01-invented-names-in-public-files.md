# Invented names in the public repository's tests and docs

Status: resolved
Type: task
Owner: Claude

## Question

This repository is public: tests and docs carry counts and invented examples, never a real company or fund name
(CLAUDE.md, "Commits, PRs and secrets"). Several tests and docs named real companies and fund sponsors. Replace
each with an invented name that keeps the case it proves.

## Checklist

- [x] Replace the real names in `CONTEXT.md`, three research notes, three specs, and the MDM and profiling tests with invented ones that keep each test's case 2026-11-18 21:26 ET
- [x] Replace the last ones found by a repository-wide search of tracked files outside `.scratch/` (the legal-form key tests, the installed-bundle test, `CONTEXT.md`, one research note, one profiling assertion) 2026-11-18 21:26 ET
- [x] Run the affected tests: 144 passed (`tests/mdm/test_names.py`, `test_quality.py`, `tests/unit/test_profiling_name_matching.py`, `tests/engine/test_company_name_key.py`); the installed-bundle test builds from the commit, so CI proves it 2026-11-18 21:26 ET
- [ ] ~~`tests/fixtures/clean_mdm/four_companies_v1/build.py` and the ADR's share-class example~~ deferred: they name real companies as a recorded fixture and a decision's example; changing the fixture changes its pinned digests, so it needs its own ticket and the operator's word
- [ ] ~~`.scratch/company-mastering/` research notes~~ deferred: working files from earlier tickets, outside the tests and docs a reader meets
- [x] Learning → skill: none (the rule is already in CLAUDE.md)
