# Simplify the tests, make them fast, delete old ones

Priority: 88, tier 1, in flight (raised by the operator, 2026-10-15). Map: [Rebuild priorities](../map.md).

Type: task (tests). Status: done, merged (#988, 2026-10-16 13:25 ET). Blocked by: none.

## Why

Operator, 2026-10-15: "simplify and review all the tests and make them performant and delete old tests".

## What the suite costs (CI on main, 2026-10-15 06:27 ET, run 38720344413; per test from the log's timestamps)

| Job | Wall time | Time in tests |
|---|---|---|
| Engine (Rust behind Python) | 5 min 32 s | 249 s (plus the Rust build and `cargo test`) |
| Integration tests (Postgres) | 4 min 58 s | 245 s |
| MDM tests | 1 min 31 s | 32 s |
| Unit tests (with architecture) | 1 min 15 s | 38 s |

3,024 tests timed. Where the time goes:
- `tests/engine/test_data_skill_bundle_postgres.py`: **208 s of the engine job's 249 s**, 85 tests. Its 16 `test_parse_then_master_runs_through_the_installed_bundle` variants take about 8.4 s each (134 s together). They share one PostgreSQL 16 server per module (`databases`), and the CLI starts in 0.12 s, so the time is in each variant's own commands: to be profiled before changing anything. `test_name_key_recipes_run_from_installed_bundle` alone takes 34 s. Only `test_the_rules_creator_runs_from_the_bundle_on_an_empty_rules_database` starts its own server.
- Integration: `test_configured_capture_postgres.py` 49 s (36 tests), `test_configured_bookkeeping_postgres.py` 21 s, `test_mdm_merge_worker_postgres.py` 16 s (3 tests), then a long tail of 5–10 s files.
- Suite size: 29 architecture, 54 engine, 45 integration, 37 MDM and 49 unit test files (about 38,000 lines), and 29 Rust test files.

## Rules for the review

- **Old:** a test whose subject is code the rebuild deleted or no longer runs (operator, 2026-09-26: the rebuild is the only system; no legacy is kept). Each one deleted lists the deleted code it guarded; a test of code still in use is never deleted to save time.
- **Fast:** start each container once per module (or session), not per test; share fixtures read once; no sleeps; a test reads no more than it proves.
- **Simple:** one test per behaviour; parametrize repeats; no copy of a helper in several files (`tests/support/`).
- The full suite runs in CI; locally only affected tests (AGENTS.md, "Tests and CI").

## Checklist

- [x] Per-test times from CI (above); the slowest files read: the bundle test, the configured capture and bookkeeping tests, the merge worker test 2026-10-15 07:04 ET
- [x] The bundle test: profile one parse-then-master variant and the name-key test, then cut what repeats across variants; time before and after
  - [x] Measured: a variant runs about ten CLI processes (a rules run, a work and a verify per profile, status, finalize); a warm worker import is 0.5 s (`source.read` 0.5 s, of which `pyarrow` 0.3 s; 4 s cold), so about 5 of its 8.4 s are process starts 2026-10-15 07:04 ET
  - [x] Six variants dropped, each a reading feature a worker-level engine test already covers in-process: parallel records (`test_parallel_records.py`), integers (`test_integer_values.py`), artifact context (`test_artifact_context.py`), selected sequences (`test_selected_sequences.py`), object records (`test_object_records.py`; the raw-person variant runs the same bundle path) and XML streaming (`test_xml_stream_worker.py`; the recovery variant streams XML too); their 9 dead branches removed (102 lines). Kept, as nothing else runs them through the installed bundle: configured, parquet records, custom step, source coercion, reference lookup (the bundle ships its reference files), raw person, combined records, choice records, streamed records, XML recovery. About 50 s off the engine job; to be confirmed by CI 2026-10-15 07:04 ET
- [ ] ~~Integration: shared containers and fixtures in the slowest files~~ deferred to ticket 98 (Integration tests share their containers and fixtures): the operator asked this PR to finish deleting old and unused tests (2026-10-16: "complete PR 988 delete old tests and unused test"); fixture sharing is a speed change measured on its own
- [x] Old tests: list each test file whose subject is retired code (architecture tests of retired scripts, `tests/support/retired_*`, silver landing, dashboards), with the evidence; delete them with their retired code where the code is unused
  - [x] Group A, the frozen silver landing API (`tests/support/retired_silver_landing_store.py`: "Frozen historical landing API; no executable consumers"): 13 unit test files, 93 tests, that exercise only that frozen copy or the frozen submission loaders (the landing passthrough tests, the staging and lookback tests, `test_loaders.py`), with `tests/support/silver_rows.py` and `edgar_warehouse/serving/silver_landing_export.py`, whose only Python users were those (infra names it in SQL and Terraform only): 3,063 lines deleted. The retirement guard (`test_retired_submission_loaders.py`) now refuses the export module too. 1,601 unit, MDM and architecture tests still collect; the guard tests pass 2026-10-15 07:02 ET. Corrected on review: two tests of the deleted `test_sec_company_address_country_code.py` guarded live code (every dbt silver model selects its landing columns; `install.sh` adds `country_code` before dbt reads it), so they moved to `test_silver_schema_snapshot.py` 2026-10-16 10:18 ET
  - [x] Architecture tests: each names files that exist, or checks on purpose that a retired one stays gone (the env generator's fixtures, the retired loaders); the dashboard tests check live scripts: none deleted 2026-10-15 07:02 ET
  - [x] Group B, the comparison oracles: every test that compared the engine with a frozen copy of an old parser now states its answer (in the test, or in an answer file written once from the oracle while the two still agreed), and each new answer was checked to fail when changed (a wrong value, a type-only change such as false to 0). Deleted, with what they guarded: `tests/support/retired_submission_loaders/` (the SEC submission loaders), `retired_company_address.py` (the landed business address), `retired_company_preparation.py` (census evidence), `retired_company_bundle.py` (the in-process Company preparation), `retired_name_census.py` (the census builder), `retired_gleif_attestation.py` (the GLEIF runtime inspector), `ticker_catalog_oracle.py` (the ticker parser), `scripts/qualification/legacy_gleif_json_oracle.py` (the GLEIF JSON reader); 13 one-time qualification scripts that compared the engine with them (`audit_company_main_semantics`, `audit_filing_semantics`, `audit_catalog_semantics`, `audit_json_sequence`, `qualify_company_main`, `_census`, `_catalog`, `_pages`, `qualify_parallel_records`, `qualify_raw_submissions`, `qualify_census_reading`, `qualify_census_names_stream`, and the crate's `whole_source_frequency.py`; their results stay recorded in `.planning`). Answer files: `tests/engine/fixtures/{company-main-matrix,filing-selection-matrix,configured-census-cases,gleif-attestation-reports}.json`, `tests/integration/fixtures/company-mastering-records.json`. Two values follow today's time (the archive hash of a zip the test builds, and the census digest over it), so the tests compute those. 440 tests of the changed files pass (38 s), and the installed GLEIF mapping test (2 min 22 s) 2026-10-16 10:13 ET
  - [x] Unused: four fixture files no test reads (`company-object.yaml`, `company-raw.yaml`, `native_company_v1.json`, `publication_v1/`); no always-skipped test (the one strict expected failure documents a known engine gap, ticket 15) 2026-10-16 10:13 ET
- [x] Simplify: the exact JSON comparisons (`require_tables`, `ordered`) into `tests/support/exact.py`, out of the deleted scripts; the converted tests are parametrized by case and answer 2026-10-16 10:13 ET
- [x] Three-axis review: GoF none; Standards: the census answers made explicit, the SEC default rows shared (`tests/support/sec_rows.py`); Spec: two live guards restored, a test with no assertion given the live cascade projection, the dropped bundle variants' prepare and type checks restated in-process, two doc links fixed 2026-10-16 10:18 ET
- [x] PR #988, CI green (6 checks), merged on the operator's words "merge one by one" 2026-10-16 13:25 ET
- [x] Learning → skill: `CLAUDE.md` and `AGENTS.md` "Tests and CI" gain: a test states its expected answer, never a frozen copy of retired code; to retire an oracle, write its answers in once while they agree, change each once to see the test fail, compute values that follow the clock. mdm-engineering "Choose the cheapest proof" unchanged: nothing here is an MDM store proof 2026-10-16 10:14 ET
