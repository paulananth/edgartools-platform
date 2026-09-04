"""Verifies write_single_workflow_definition's sec_fetch_active lease wiring
(release-readiness ticket 84, implementing ticket 80's Phase 1 primitive)
for bootstrap_full and targeted_resync -- the two SEC-fetching commands
among the 6 workflows sharing this function that need the cross-command
lease. load_daily_form_index_for_date, catch_up_daily_form_index,
gold_refresh, and seed_universe stay unwrapped. (full_reconcile was a
seventh member of this set until it was decommissioned entirely.)

Generates the real write_single_workflow_definition() state machine JSON
(same driver mechanism as test_daily_identity_refresh_state_machine.py).
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"

_SWD_START = "write_single_workflow_definition() {\n"
_SWD_END = "\nPY\n}\n"

_FAKE_TASK_ARN = "arn:fake-wh-task"
_FAKE_BRONZE_BUCKET = "fake-bronze-bucket"


def _extract_function_source() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index(_SWD_START)
    end = text.index(_SWD_END, start) + len(_SWD_END)
    return text[start:end]


def _generate_definition(
    default_command: str = "States.Array('bootstrap-full', '--run-id', $$.Execution.Name)",
    cik_command: str = "",
    wrap_with_sec_fetch_lease: str = "",
) -> dict:
    fn_source = _extract_function_source()
    tmp_root = REPO_ROOT / ".pytest_cache" / "sec_fetch_lease_single_workflow_wiring_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        fn_file = tmp_path / "swd_fn.sh"
        fn_file.write_text(fn_source, encoding="utf-8")
        out_file = tmp_path / "definition.json"

        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            'PUBLIC_SUBNET_IDS_JSON=\'["subnet-aaaa","subnet-bbbb"]\'\n'
            'SECURITY_GROUP_IDS_JSON=\'["sg-cccc"]\'\n'
            f'source "{fn_file.as_posix()}"\n'
            f'write_single_workflow_definition "{out_file.as_posix()}" "{_FAKE_TASK_ARN}" '
            f'"{default_command}" "{cik_command}" "{_FAKE_BRONZE_BUCKET}" "{wrap_with_sec_fetch_lease}"\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            ["bash", driver.as_posix()], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise AssertionError(
                f"single-workflow definition generation failed:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        return json.loads(out_file.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bootstrap_full_definition() -> dict:
    """bootstrap_full has no cik_command override (matches its real
    workflow_cik_command_expression, which returns empty for this
    workflow)."""
    return _generate_definition(
        default_command="States.Array('bootstrap-full', '--run-id', $$.Execution.Name)",
        cik_command="",
        wrap_with_sec_fetch_lease="true",
    )


@pytest.fixture(scope="module")
def targeted_resync_definition() -> dict:
    """targeted_resync supports a cik_list override (matches its real
    workflow_cik_command_expression)."""
    return _generate_definition(
        default_command="States.Array('targeted-resync', '--run-id', $$.Execution.Name)",
        cik_command="States.Array('targeted-resync', '--cik-list', $.cik_list, '--run-id', $$.Execution.Name)",
        wrap_with_sec_fetch_lease="true",
    )


@pytest.fixture(scope="module")
def unwrapped_definition() -> dict:
    """gold_refresh (a stand-in for the 5 non-SEC-fetching workflows in the
    loop) must be completely untouched -- wrap_with_sec_fetch_lease=""."""
    return _generate_definition(
        default_command="States.Array('gold-refresh', '--run-id', $$.Execution.Name)",
        cik_command="",
        wrap_with_sec_fetch_lease="",
    )


def test_bootstrap_full_acquires_lease_before_run_and_releases_before_end(
    bootstrap_full_definition,
) -> None:
    states = bootstrap_full_definition["States"]
    assert bootstrap_full_definition["StartAt"] == "AcquireSecFetchLease"

    acquire = states["AcquireSecFetchLease"]
    cmd = acquire["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "acquire-sec-fetch-lease" in cmd
    assert acquire["ResultPath"] is None
    assert acquire["Next"] == "ReadSecFetchLeaseResult"

    read_result = states["ReadSecFetchLeaseResult"]
    assert read_result["Resource"] == "arn:aws:states:::aws-sdk:s3:getObject"
    assert read_result["ResultPath"] == "$.sec_fetch_lease_check"
    assert read_result["Next"] == "SecFetchLeaseAcquiredCheck"

    check = states["SecFetchLeaseAcquiredCheck"]
    assert check["Type"] == "Choice"
    assert check["Choices"][0]["Variable"] == "$.sec_fetch_lease_check.parsed.lease_acquired"
    assert check["Choices"][0]["BooleanEquals"] is True
    assert check["Choices"][0]["Next"] == "RunWarehouseTask"
    assert check["Default"] == "SecFetchDeferred"

    run_task = states["RunWarehouseTask"]
    assert run_task["Next"] == "ReleaseSecFetchLease"

    release = states["ReleaseSecFetchLease"]
    cmd = release["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "release-sec-fetch-lease" in cmd
    assert release["ResultPath"] is None
    assert release["End"] is True
    assert release["Catch"] == [
        {"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "ReleaseSecFetchLeaseFailedNonFatal"}
    ]

    fallback = states["ReleaseSecFetchLeaseFailedNonFatal"]
    assert fallback["Type"] == "Pass"
    assert fallback["End"] is True

    deferred = states["SecFetchDeferred"]
    assert deferred["End"] is True
    assert deferred["Parameters"]["disposition"] == "sec_fetch_deferred"


def test_bootstrap_full_run_warehouse_task_releases_lease_on_failure(
    bootstrap_full_definition,
) -> None:
    """release-readiness ticket 86: RunWarehouseTask had no Catch -- a real
    failure (an immutable-object content conflict, found live during
    ticket 84's own verification) wedged sec_fetch_active for the full 16h
    stale-reclaim window instead of releasing it. The Catch must release
    the lease and still fail the execution (ExecutionsFailed/alarm
    visibility preserved), not silently succeed like
    ReleaseSecFetchLease's own happy-path Catch does."""
    states = bootstrap_full_definition["States"]
    run_task = states["RunWarehouseTask"]
    assert run_task["Catch"] == [
        {"ErrorEquals": ["States.ALL"], "ResultPath": "$.sec_fetch_task_error", "Next": "ReleaseSecFetchLeaseAfterFailure"}
    ]

    release_after_failure = states["ReleaseSecFetchLeaseAfterFailure"]
    cmd = release_after_failure["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "release-sec-fetch-lease" in cmd
    assert release_after_failure["ResultPath"] is None
    assert release_after_failure["Next"] == "SecFetchTaskFailed"
    # Even if the release-after-failure task itself fails, still reach Fail --
    # never silently succeed on a real work failure.
    assert release_after_failure["Catch"] == [
        {"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "SecFetchTaskFailed"}
    ]

    failed = states["SecFetchTaskFailed"]
    assert failed["Type"] == "Fail"
    assert failed["ErrorPath"] == "$.sec_fetch_task_error.Error"
    assert failed["CausePath"] == "$.sec_fetch_task_error.Cause"


def test_bootstrap_full_no_operator_notification(bootstrap_full_definition) -> None:
    """Unlike daily_incremental's identity-refresh lease, these ad-hoc
    operator-triggered workflows get no SNS notification on defer -- the
    operator is already watching the run they triggered."""
    assert "NotifySecFetchDeferred" not in bootstrap_full_definition["States"]


def test_targeted_resync_lease_wraps_both_cik_list_branches(targeted_resync_definition) -> None:
    """The lease gates entry into the HasCikListOverride Choice itself, so
    both the default and cik_list-override Run branches are protected, and
    both converge on the same ReleaseSecFetchLease afterward."""
    states = targeted_resync_definition["States"]
    assert targeted_resync_definition["StartAt"] == "AcquireSecFetchLease"

    check = states["SecFetchLeaseAcquiredCheck"]
    assert check["Choices"][0]["Next"] == "HasCikListOverride"

    has_cik_override = states["HasCikListOverride"]
    assert has_cik_override["Type"] == "Choice"
    assert has_cik_override["Choices"][0]["Next"] == "RunWarehouseTaskWithCikList"
    assert has_cik_override["Default"] == "RunWarehouseTaskDefault"

    assert states["RunWarehouseTaskDefault"]["Next"] == "ReleaseSecFetchLease"
    assert states["RunWarehouseTaskWithCikList"]["Next"] == "ReleaseSecFetchLease"

    release = states["ReleaseSecFetchLease"]
    assert release["End"] is True


def test_targeted_resync_both_run_branches_release_lease_on_failure(
    targeted_resync_definition,
) -> None:
    """release-readiness ticket 86: both RunWarehouseTaskDefault and
    RunWarehouseTaskWithCikList (targeted_resync's two Run branches) must
    release sec_fetch_active and still fail on a real work failure, not
    leave it wedged for 16h."""
    states = targeted_resync_definition["States"]
    expected_catch = [
        {"ErrorEquals": ["States.ALL"], "ResultPath": "$.sec_fetch_task_error", "Next": "ReleaseSecFetchLeaseAfterFailure"}
    ]
    assert states["RunWarehouseTaskDefault"]["Catch"] == expected_catch
    assert states["RunWarehouseTaskWithCikList"]["Catch"] == expected_catch

    release_after_failure = states["ReleaseSecFetchLeaseAfterFailure"]
    assert release_after_failure["Next"] == "SecFetchTaskFailed"
    assert states["SecFetchTaskFailed"]["Type"] == "Fail"


def test_sec_fetch_lease_read_result_key_matches_the_real_path_resolver(
    bootstrap_full_definition, targeted_resync_definition,
) -> None:
    """The hand-typed S3 key in ReadSecFetchLeaseResult must tie to
    sec_fetch_lease_path()'s real template -- see the identical test in
    test_daily_identity_refresh_state_machine.py for why (ReadSecFetchLeaseResult
    has no Catch, so a drifted key hard-fails the execution instead of
    deferring)."""
    from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver

    relative_template = default_path_resolver().sec_fetch_lease_path("RUNID_PLACEHOLDER").replace(
        "RUNID_PLACEHOLDER", "{}"
    )
    expected_key_expr = (
        f"States.Format('warehouse/bronze/{relative_template}', $$.Execution.Name)"
    )
    for definition in (bootstrap_full_definition, targeted_resync_definition):
        key_expr = definition["States"]["ReadSecFetchLeaseResult"]["Parameters"]["Key.$"]
        assert key_expr == expected_key_expr


def test_unwrapped_workflow_has_no_sec_fetch_lease_states(unwrapped_definition) -> None:
    """gold_refresh (representing the 5 non-SEC-fetching workflows in the
    loop) must be byte-for-byte the original shape -- no lease states leak
    in when wrap_with_sec_fetch_lease is empty."""
    assert unwrapped_definition["StartAt"] == "RunWarehouseTask"
    assert unwrapped_definition["States"]["RunWarehouseTask"]["End"] is True
    assert "Catch" not in unwrapped_definition["States"]["RunWarehouseTask"]
    for leaked_state in (
        "AcquireSecFetchLease",
        "ReadSecFetchLeaseResult",
        "SecFetchLeaseAcquiredCheck",
        "SecFetchDeferred",
        "ReleaseSecFetchLease",
        "ReleaseSecFetchLeaseFailedNonFatal",
        "ReleaseSecFetchLeaseAfterFailure",
        "SecFetchTaskFailed",
    ):
        assert leaked_state not in unwrapped_definition["States"]
