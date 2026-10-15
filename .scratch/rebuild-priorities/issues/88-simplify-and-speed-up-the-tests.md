# Simplify the tests, make them fast, delete old ones

Priority: 88, tier 1, in flight (raised by the operator, 2026-10-15). Map: [Rebuild priorities](../map.md).

Type: task (tests). Status: claimed (Claude, 2026-10-15 ET, branch `claude/test-suite-review`). Blocked by: none.

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

- [ ] Per-test times from CI (done above); the 20 slowest files read
- [ ] The bundle test: profile one parse-then-master variant and the name-key test, then cut what repeats across variants; time before and after
- [ ] Integration: shared containers and fixtures in the slowest files; time before and after
- [ ] Old tests: list each test file whose subject is retired code (architecture tests of retired scripts, `tests/support/retired_*`, silver landing, dashboards), with the evidence; delete them with their retired code where the code is unused
  - [x] Group A, the frozen silver landing API (`tests/support/retired_silver_landing_store.py`: "Frozen historical landing API; no executable consumers"): 13 unit test files, 93 tests, that exercise only that frozen copy or the frozen submission loaders (the landing passthrough tests, the staging and lookback tests, `test_loaders.py`), with `tests/support/silver_rows.py` and `edgar_warehouse/serving/silver_landing_export.py`, whose only Python users were those (infra names it in SQL and Terraform only): 3,063 lines deleted. The retirement guard (`test_retired_submission_loaders.py`) now refuses the export module too. 1,601 unit, MDM and architecture tests still collect; the guard tests pass 2026-10-15 07:02 ET
  - [x] Architecture tests: each names files that exist, or checks on purpose that a retired one stays gone (the env generator's fixtures, the retired loaders); the dashboard tests check live scripts: none deleted 2026-10-15 07:02 ET
  - [ ] Group B, the comparison oracles (`retired_submission_loaders`, `retired_name_census`, `retired_company_*`, `retired_gleif_attestation`): engine tests compare the configured engine with these frozen copies of the old parsers, the only check of those contracts' output. Kept until each test checks its expected output directly (a golden file), then deleted with the oracle
- [ ] Simplify: duplicated helpers into `tests/support/`; repeated tests parametrized
- [ ] Three-axis review; PR, CI green (job times before and after in the PR), merge on the operator's word
- [ ] Learning → skill: the test rules into `AGENTS.md` "Tests and CI" and mdm-engineering "Choose the cheapest proof"
