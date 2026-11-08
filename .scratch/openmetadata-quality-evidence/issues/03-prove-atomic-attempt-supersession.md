# Prove Atomic Attempt Supersession

Type: task
Status: resolved
Blocked by: none
Blocks: 05, 07
Labels: wayfinder:task

## Question

Can an attempt superseded after the admission precheck still be prevented from
completing at the atomic database boundary under concurrent execution?

## Checklist

- [x] Made the PostgreSQL proof runnable with the compiled `source_contract` extension and retained the prior assertions. Verified by the package build and native-module import below. 2026-11-07 19:17 ET.
- [x] Exercised the race after admission precheck with running and verified replacements. Verified by the PostgreSQL testmon run below. 2026-11-07 19:17 ET.
- [x] Confirmed stale attempts cannot complete or replace replacement evidence. Both DB rejection outcomes and the surviving replacement state/evidence are asserted. 2026-11-07 19:17 ET.
- [x] Ran retry, concurrency, precision, flag/exception and historical-result checks. The 18-test focused selection passed; the testmon run is recorded below. 2026-11-07 19:19 ET.
- [x] Recorded commands, results and remaining gates in Answer. 2026-11-07 19:17 ET.
- [x] Learning → skill: none; this is a test-specific interleaving, not a reusable operating rule. 2026-11-07 19:17 ET.

## Answer

Yes. The test pauses stale attempt A at the artifact-report read after its Python admission precheck. While A is paused, it expires A's lease and claims replacement B.

- If B is still running, A's atomic finish is rejected as `Stale attempt`; B remains running with its attempt.
- If B is verified first, A's finish is rejected as `Completion evidence changed`; B's report reference remains stored.

The original running-replacement assertions from the prior integration proof remain in the first case.

The compiled extension setup succeeded:

```bash
uv sync --all-extras --group dev --reinstall-package source-contract
uv run --no-sync python -c 'import source_contract; from pathlib import Path; print(Path(source_contract.source_contract.__file__).resolve())'
```

The import resolved to `.venv/lib/python3.12/site-packages/source_contract/source_contract.abi3.so`.

The testmon-active run:

```bash
TESTMON_DATAFILE=~/.cache/edgartools/testmondata uv run --no-sync pytest --testmon tests/integration/test_configured_bookkeeping_postgres.py tests/unit/test_bookkeeping_quality.py tests/unit/test_silver_land_quality.py tests/unit/test_rules_catalog.py
```

Result: 70 passed, 63 deselected in 76.00s.

The supplementary focused run:

```bash
TESTMON_DATAFILE=~/.cache/edgartools/testmondata uv run --no-sync pytest --testmon \
  tests/integration/test_configured_bookkeeping_postgres.py::test_attempt_superseded_after_admission_precheck_is_refused_atomically \
  tests/integration/test_configured_bookkeeping_postgres.py::test_a_lease_lapsing_while_the_verifier_runs_refuses_the_late_admission \
  tests/integration/test_configured_bookkeeping_postgres.py::test_renewal_takeover_and_stale_completion \
  tests/integration/test_configured_bookkeeping_postgres.py::test_a_lapsed_report_is_verified_not_worked_again \
  tests/unit/test_bookkeeping_quality.py \
  tests/unit/test_silver_land_quality.py \
  tests/unit/test_rules_catalog.py::test_catalog_partial_publish_failure_requires_readback_before_retry \
  tests/unit/test_rules_catalog.py::test_publish_stops_after_one_quality_result_correction \
  tests/unit/test_rules_catalog.py::test_check_says_when_the_row_counts_of_a_result_differ
```

Result: 18 passed in 10.24s. Pytest disabled testmon selection for these manually named nodes.

This closes only the atomic supersession proof. Version-2 quality evidence remains disabled. The recovery maximum, completed-load end-to-end verification and shipped-UI observation remain in their own open tickets.
