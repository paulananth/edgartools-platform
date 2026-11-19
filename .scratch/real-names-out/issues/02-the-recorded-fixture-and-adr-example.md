# The recorded four-company fixture and the ADR example use invented names

Status: open
Type: task
Owner: Claude

Operator, 2026-11-18: "fix Real company names: the four_companies_v1 fixture and one ADR example still name real companies.
Changing the fixture needs your word because its digests are pinned" (the operator's word is this instruction). Ticket 01
left both because the fixture is a recording and its hash is pinned.

## Findings

- `tests/fixtures/clean_mdm/four_companies_v1/` was recorded from real SEC submissions and the GLEIF golden copy: four real
  companies (names, CIKs, EINs, addresses, LEIs) and two real individuals' names. Only the `sec` rows and `person_raw.jsonl` are
  read (by `tests/support/fresh_mastering.py`, and `person_raw.jsonl` by the installed-bundle test); the GLEIF records are read
  by no test.
- One test pins the cohort's records as a hash (`tests/mdm/test_fresh_mastering_cohort.py`).

## Parts

- [x] Replace the fixture with an invented cohort (two operating companies, two other filers, two individual filers; invented names, CIKs and ticker symbols), written by `build.py` from invented tables: no provider input, no GLEIF records (nothing read them), no retained-bronze dependency 2026-11-18 22:11 ET
- [x] The pinned cohort hash fails against the new rows (`assert '4c5f6ed3...' == '3f353edb...'`) and is changed once to the new value; it is the same on a second run (`tests/mdm/test_fresh_mastering_cohort.py`, 2 passed twice) 2026-11-18 22:11 ET
- [x] `tests/support/fresh_mastering.py` names the invented CIKs and tickers and drops the two real LEIs it no longer uses 2026-11-18 22:11 ET
- [x] ADR 0015's share-class and sponsor examples are invented or unnamed 2026-11-18 22:11 ET
- [ ] ~~The other files that name real companies or hold their identifiers~~ deferred to its own ticket: about 35 files under `tests/`, `docs/` and `skills/` still mention real companies or CIKs (counted by a search for a handful of names, so a floor, not a total), among them `tests/mdm/*`, `tests/engine/*`, `tests/integration/fixtures/company-mastering-records.json`, `docs/research/13f-alphabet-class-a-c-2026-09-25.md`; three more files hold a real individual's name as a test input (`tests/engine/test_sec_configured_fields.py`, `tests/storage_adapters/test_mastering_undecidable.py`, `docs/specs/person/consumer.md`), the first to take up; each is a test input or a research note whose expectations depend on the value, so each needs its own look
- [ ] Learning → skill: none (the rule is in CLAUDE.md)
