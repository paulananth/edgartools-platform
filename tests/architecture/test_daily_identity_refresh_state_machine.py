"""Verifies daily_incremental's bounded Daily Identity Refresh wiring
(release-readiness ticket 45/49: "Decide whether/how to narrow
daily_incremental's Stage 0 and set its actual schedule").

Generates the real write_warehouse_mdm_gold_definition() state machine JSON
(same driver mechanism as
tests/architecture/test_gold_affecting_commands_task_sizing.py) and asserts:

- daily_incremental's default path (no refresh_mode input, or refresh_mode
  != "backstop") routes through the new bounded FindCompaniesWithNewFilings
  -> CaptureCompanyIdentityBatches stages, NOT the full-universe ComputeWindows
  path that took 10h16m alone on the first prod execution (ticket 45's
  evidence).
- refresh_mode="backstop" routes through the same explicit-CIK batch Map as
  daily mode, but its pre-stage emits the complete active company-eligible
  universe rather than an index-impacted subset.

(bootstrap, the other former workflow_name value for this same builder, was
retired by state-machine-consolidation ticket 06 -- its dedicated
regression tests here, which proved daily_incremental's new stages never
leaked into it, were removed alongside it.)
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"

_WMG_START = "write_warehouse_mdm_gold_definition() {\n"
_WMG_END = "\nPY\n}\n"

# write_warehouse_mdm_gold_definition calls command_task_profile()
# internally (task-profile-consolidation ticket 02) to resolve
# CaptureAndVerifyNewFilings's profile -- extracted and sourced alongside it below.
_COMMAND_TASK_PROFILE_START = "command_task_profile() {\n"
_COMMAND_TASK_PROFILE_END = "\n}\n"

_FAKE_MEDIUM_ARN = "arn:fake-wh-medium"
_FAKE_LARGE_ARN = "arn:fake-wh-large"
_FAKE_ALERT_TOPIC_ARN = "arn:aws:sns:us-east-1:000000000000:fake-operator-alerts"


def _extract_function_source() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index(_WMG_START)
    end = text.index(_WMG_END, start) + len(_WMG_END)
    return text[start:end]


def _extract_command_task_profile_source() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index(_COMMAND_TASK_PROFILE_START)
    end = text.index(_COMMAND_TASK_PROFILE_END, start) + len(_COMMAND_TASK_PROFILE_END)
    return text[start:end]


def _generate_definition(workflow_name: str, alert_topic_arn: str = _FAKE_ALERT_TOPIC_ARN) -> dict:
    fn_source = _extract_function_source()
    command_task_profile_source = _extract_command_task_profile_source()
    tmp_root = REPO_ROOT / ".pytest_cache" / "daily_identity_refresh_state_machine_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        fn_file = tmp_path / "wmg_fn.sh"
        fn_file.write_text(fn_source, encoding="utf-8")
        command_task_profile_file = tmp_path / "command_task_profile_fn.sh"
        command_task_profile_file.write_text(command_task_profile_source, encoding="utf-8")
        out_file = tmp_path / f"{workflow_name}.json"

        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'fail() { echo "ERROR: $*" >&2; exit 1; }\n'
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            'PUBLIC_SUBNET_IDS_JSON=\'["subnet-aaaa","subnet-bbbb"]\'\n'
            'SECURITY_GROUP_IDS_JSON=\'["sg-cccc"]\'\n'
            f'SCRIPT_DIR="{(REPO_ROOT / "infra" / "scripts").as_posix()}"\n'
            f'source "{command_task_profile_file.as_posix()}"\n'
            f'source "{fn_file.as_posix()}"\n'
            f'write_warehouse_mdm_gold_definition "{out_file.as_posix()}" '
            f'"{_FAKE_MEDIUM_ARN}" "{_FAKE_LARGE_ARN}" '
            f'"{workflow_name}" "fake-bronze-bucket" "{alert_topic_arn}" '
            '"arn:fake-mdm-machine"\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            ["bash", driver.as_posix()], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise AssertionError(
                f"{workflow_name} definition generation failed:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        return json.loads(out_file.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def daily_incremental_definition() -> dict:
    return _generate_definition("daily_incremental")


def test_daily_incremental_validates_operator_input_before_refresh_mode(
    daily_incremental_definition,
) -> None:
    assert daily_incremental_definition["StartAt"] == "ValidateForceInput"
    assert daily_incremental_definition["States"]["ForceDefault"]["Next"] == (
        "RefreshModeCheck"
    )


def test_daily_incremental_default_path_is_bounded_not_full_universe(daily_incremental_definition) -> None:
    """The Choice state's Default (no refresh_mode, or anything other than
    'backstop') must route to the new bounded stage, not the full-universe
    ComputeWindows path that caused the 10h16m Stage0 runtime."""
    states = daily_incremental_definition["States"]
    refresh_mode = states["RefreshMode"]
    assert refresh_mode["Type"] == "Choice"
    assert refresh_mode["Default"] == "FindCompaniesWithNewFilings"

    compute_window = states["FindCompaniesWithNewFilings"]
    cmd = compute_window["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "compute-identity-refresh-window" in cmd
    assert "'--mode', 'daily'" in cmd
    assert cmd.count("States.Array(") == 1, (
        "the generated daily refresh command must contain exactly one intrinsic "
        "constructor; duplicated fragments make the ECS override invalid"
    )
    assert compute_window["Next"] == "CaptureCompanyIdentityBatches"

    bounded_stage0 = states["CaptureCompanyIdentityBatches"]
    assert bounded_stage0["Type"] == "Map"
    assert bounded_stage0["Next"] == "PublishCompanyIdentityUpdates"
    item_reader_key = bounded_stage0["ItemReader"]["Parameters"]["Key.$"]
    assert "cik_batches.jsonl" in item_reader_key, (
        "bounded Stage0 must read the cik_list batches file (seed-universe's batch shape), "
        f"got {item_reader_key!r}"
    )
    inner_cmd = bounded_stage0["ItemProcessor"]["States"]["RunCompanyIdentityBatch"][
        "Parameters"
    ]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "--cik-list" in inner_cmd
    assert "company-identity" in inner_cmd
    assert "--identity-refresh-run-id" in inner_cmd
    assert "$.identity_refresh_run_id" in inner_cmd
    assert "$$.Execution.Name" not in inner_cmd

    item_selector = bounded_stage0["ItemSelector"]
    assert item_selector == {
        "cik_list.$": "$$.Map.Item.Value.cik_list",
        "identity_refresh_run_id.$": "$$.Execution.Name",
    }

    reducer = states["PublishCompanyIdentityUpdates"]
    reducer_cmd = reducer["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "reduce-identity-refresh" in reducer_cmd
    assert reducer["Next"] == "CaptureAndVerifyNewFilings"


def test_reduce_identity_refresh_runs_on_the_large_task_definition(daily_incremental_definition) -> None:
    """Release-readiness ticket 83: a real prod run was OOM-killed (exit 137)
    on the medium (4096MB) task definition mid-merge on the largest
    protected table. Must run on large (8192MB), matching the
    gold-build-memory-reliability precedent's CaptureAndVerifyNewFilings move --
    confirmed to fail against the pre-fix wh_medium_arn wiring."""
    reducer = daily_incremental_definition["States"]["PublishCompanyIdentityUpdates"]
    assert reducer["Parameters"]["TaskDefinition"] == _FAKE_LARGE_ARN


def test_release_lease_runs_on_the_large_task_definition(daily_incremental_definition) -> None:
    """Release-readiness ticket 89: ReleaseLease's existing Catch (see
    test_release_lease_failure_is_non_fatal) only stops a release failure
    from marking an otherwise-successful gold build FAILED -- it does not
    make the release succeed. Confirmed live in prod (2026-08-06): a real
    run's ReleaseLease task OOM-killed (exit 137) on medium (4096MB) on
    all 4 attempts, identically to ticket 83's PublishCompanyIdentityUpdates
    failure and for the same reason -- it hydrates the full canonical
    silver.duckdb (1.27GB and growing) for what is otherwise a single-row
    UPDATE, right after PublishCompanyIdentityUpdates/GoldRefresh just made
    canonical heavier within the same run. Every retry hit the Catch and
    left daily_identity_refresh permanently held with released_at NULL,
    silently -- the execution still reported SUCCEEDED. Must run on large
    (8192MB), the same fix ticket 83 already applied to PublishCompanyIdentityUpdates
    immediately above it -- confirmed to fail against the pre-fix
    wh_medium_arn wiring."""
    release_lease = daily_incremental_definition["States"]["ReleaseLease"]
    assert release_lease["Parameters"]["TaskDefinition"] == _FAKE_LARGE_ARN


def test_daily_incremental_enforces_the_eighteen_hour_execution_bound(
    daily_incremental_definition,
) -> None:
    assert daily_incremental_definition["TimeoutSeconds"] == 18 * 60 * 60


def test_daily_incremental_backstop_uses_complete_company_eligible_universe(
    daily_incremental_definition,
) -> None:
    """Backstop must use the shared company-eligibility contract and explicit
    CIK batches, never the old offset-based all-entity path."""
    states = daily_incremental_definition["States"]
    refresh_mode = states["RefreshMode"]
    backstop_choice = next(
        c for c in refresh_mode["Choices"] if c.get("StringEquals") == "backstop"
    )
    assert backstop_choice["Next"] == "ComputeIdentityBackstopUniverse"

    compute_backstop = states["ComputeIdentityBackstopUniverse"]
    cmd = compute_backstop["Parameters"]["Overrides"]["ContainerOverrides"][0][
        "Command.$"
    ]
    assert "compute-identity-refresh-window" in cmd
    assert "'--mode', 'backstop'" in cmd
    assert compute_backstop["Next"] == "CaptureCompanyIdentityBatches"

    assert "ComputeWindows" not in states
    assert "Stage0CompanyIdentity" not in states


def test_daily_incremental_both_modes_share_explicit_cik_stage0(
    daily_incremental_definition,
) -> None:
    states = daily_incremental_definition["States"]
    assert states["FindCompaniesWithNewFilings"]["Next"] == (
        "CaptureCompanyIdentityBatches"
    )
    assert states["ComputeIdentityBackstopUniverse"]["Next"] == (
        "CaptureCompanyIdentityBatches"
    )
    assert states["CaptureCompanyIdentityBatches"]["Next"] == "PublishCompanyIdentityUpdates"


# ---------------------------------------------------------------------------
# Lease wiring (go-live follow-up to ticket 49): AcquireLease -> ReadLeaseResult
# -> LeaseAcquiredCheck -> {RefreshMode | Deferred}, and ReleaseLease at the end.
# ---------------------------------------------------------------------------


def test_refresh_mode_resolution_routes_through_acquire_lease(daily_incremental_definition) -> None:
    """Both RefreshModeCheck's explicit-input branch and RefreshModeDefault
    must route to AcquireLease -- the lease must be acquired before either
    refresh mode is chosen, not after."""
    states = daily_incremental_definition["States"]
    refresh_mode_check = states["RefreshModeCheck"]
    assert refresh_mode_check["Choices"][0]["Next"] == "AcquireLease"
    assert states["RefreshModeDefault"]["Next"] == "AcquireLease"


def test_acquire_lease_preserves_refresh_mode_via_result_path_null(daily_incremental_definition) -> None:
    """Regression guard for the D-15 bug class (see the identical FetchAdvBulk
    test in test_daily_incremental_state_machine.py): an ecs:runTask.sync Task
    without ResultPath=null replaces $ entirely with its own result, destroying
    $.refresh_mode before RefreshMode's Choice can read it downstream."""
    acquire_lease = daily_incremental_definition["States"]["AcquireLease"]
    assert acquire_lease["ResultPath"] is None
    cmd = acquire_lease["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "acquire-identity-refresh-lease" in cmd
    assert "$.refresh_mode" in cmd
    assert acquire_lease["Next"] == "ReadLeaseResult"


def test_read_lease_result_uses_s3_getobject_and_parses_json_body(daily_incremental_definition) -> None:
    """ecs:runTask.sync never surfaces app-level stdout to a Choice state, so
    the lease decision must come back through an S3 side-channel read, not a
    (nonexistent) Task result field."""
    read_lease_result = daily_incremental_definition["States"]["ReadLeaseResult"]
    assert read_lease_result["Resource"] == "arn:aws:states:::aws-sdk:s3:getObject"
    key_expr = read_lease_result["Parameters"]["Key.$"]
    assert "States.StringToJson($.Body)" in read_lease_result["ResultSelector"]["parsed.$"]
    assert read_lease_result["ResultPath"] == "$.lease_check"
    assert read_lease_result["Next"] == "LeaseAcquiredCheck"


def test_read_lease_result_key_matches_the_real_path_resolver(daily_incremental_definition) -> None:
    """The deploy script's ReadLeaseResult key is a separate, hand-typed
    string from acquire-identity-refresh-lease's own write path (dataset_
    path_catalog.identity_refresh_lease_path(), backed by warehouse_paths.
    properties) -- nothing in Python/bash ties them together the way
    IDENTITY_REFRESH_LEASE_NAME ties the lease's name together. This test is
    that tie: if the .properties template ever changes, this fails loudly
    instead of ReadLeaseResult silently reading the wrong S3 key in prod."""
    from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver

    relative_template = default_path_resolver().identity_refresh_lease_path("RUNID_PLACEHOLDER").replace(
        "RUNID_PLACEHOLDER", "{}"
    )
    expected_key_expr = (
        f"States.Format('warehouse/bronze/{relative_template}', $$.Execution.Name)"
    )
    key_expr = daily_incremental_definition["States"]["ReadLeaseResult"]["Parameters"]["Key.$"]
    assert key_expr == expected_key_expr


def test_lease_acquired_check_is_fail_closed_on_default(daily_incremental_definition) -> None:
    """Only an explicit, successfully-parsed lease_acquired=True proceeds to
    ApplyEffectiveRefreshMode -- a successfully-parsed lease_acquired=False
    falls through Default to Deferred. This is deliberately inverted from
    this file's other Choice states (where Default is the common path) for
    safety: a lease miss must never be mistaken for a lease hit.

    This Choice only ever runs at all if ReadLeaseResult's getObject/
    StringToJson succeeded -- a missing or corrupt lease_result.json fails
    that upstream Task outright (see test_read_lease_result_has_no_catch),
    it does NOT reach this Choice and silently resolve to Deferred. Don't
    conflate "lease busy" (this Choice's Default) with "something is
    actually broken" (an upstream Task failure) -- they're different
    dispositions on purpose."""
    check = daily_incremental_definition["States"]["LeaseAcquiredCheck"]
    assert check["Type"] == "Choice"
    assert check["Choices"][0]["Variable"] == "$.lease_check.parsed.lease_acquired"
    assert check["Choices"][0]["BooleanEquals"] is True
    assert check["Choices"][0]["Next"] == "ApplyEffectiveRefreshMode"
    assert check["Default"] == "NotifyDeferred"


def test_apply_effective_refresh_mode_overwrites_refresh_mode_from_lease_result(
    daily_incremental_definition,
) -> None:
    """acquire-identity-refresh-lease resolves the *effective* mode server-side
    (an overdue backstop, persisted on pipeline_run_lease.backstop_overdue,
    overrides whatever the trigger's own regular schedule slot requested --
    release-readiness ticket 45's 'prioritize the next available slot'
    requirement) and writes it into lease_result.json's 'mode' field. This
    Pass state overwrites the *raw* $.refresh_mode (set before AcquireLease
    ever ran, straight from the trigger payload) with that resolved value,
    so RefreshMode's dispatch below reflects the lease's decision, not the
    original request. Next is AcquireSecFetchLease, not RefreshMode directly
    (release-readiness ticket 84) -- the cross-command sec_fetch_active
    lease gates entry into RefreshMode's SEC-calling stages."""
    state = daily_incremental_definition["States"]["ApplyEffectiveRefreshMode"]
    assert state["Type"] == "Pass"
    assert state["InputPath"] == "$.lease_check.parsed.mode"
    assert state["ResultPath"] == "$.refresh_mode"
    assert state["Next"] == "AcquireSecFetchLease"


def test_read_lease_result_has_no_catch(daily_incremental_definition) -> None:
    """Deliberate, not an oversight (see the deploy script's comment above
    AcquireLease): a missing/corrupt lease_result.json must fail the
    execution loudly, not be silently swallowed into the benign 'lease busy'
    Deferred disposition. If this test ever needs to change because someone
    adds a Catch here, re-read that comment first -- it explains why that
    would mask real bugs as false-reassuring 'deferred, all good' events."""
    assert "Catch" not in daily_incremental_definition["States"]["ReadLeaseResult"]


def test_deferred_notifies_the_operator_before_the_terminal_disposition(
    daily_incremental_definition,
) -> None:
    """Deferred's own execution output must carry a labeled disposition, not
    just an app-level event buried in CloudWatch -- found in code review
    that the original bare Pass state relied entirely on $ passthrough for
    this, which worked but wasn't operator-legible at a glance."""
    states = daily_incremental_definition["States"]
    check = states["LeaseAcquiredCheck"]
    assert check["Default"] == "NotifyDeferred"

    notification = states["NotifyDeferred"]
    assert notification["Type"] == "Task"
    assert notification["Resource"] == "arn:aws:states:::sns:publish"
    assert notification["Parameters"] == {
        "TopicArn": _FAKE_ALERT_TOPIC_ARN,
        "Subject": "EdgarTools Daily Identity Refresh deferred",
        "Message.$": "States.JsonToString($.lease_check.parsed)",
    }
    assert notification["ResultPath"] is None
    assert notification["Next"] == "Deferred"

    deferred = states["Deferred"]
    assert deferred["Type"] == "Pass"
    assert deferred["End"] is True
    assert deferred["Parameters"]["disposition"] == "deferred"
    assert deferred["Parameters"]["lease_check.$"] == "$.lease_check.parsed"
    assert deferred["ResultPath"] == "$.deferred_summary"


def test_gold_refresh_routes_to_release_lease_not_end(daily_incremental_definition) -> None:
    """daily_incremental's GoldRefresh must release the lease before ending
    -- the function's shared `gold` object defaults to is_end=True (the
    general/standalone shape) and is only mutated inside this
    daily_incremental-only branch."""
    gold_refresh = daily_incremental_definition["States"]["FactPublishtoGold"]
    assert "End" not in gold_refresh
    assert gold_refresh["Next"] == "ReleaseLease"

    release_lease = daily_incremental_definition["States"]["ReleaseLease"]
    assert release_lease["End"] is True
    cmd = release_lease["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "release-identity-refresh-lease" in cmd


def test_release_lease_failure_is_non_fatal(daily_incremental_definition) -> None:
    """A release hiccup must not mark an otherwise-successful gold build
    FAILED -- the 18h stale-lease reclaim in acquire_pipeline_run_lease is
    the actual safety net for a wedged lease, not a fully-caught SFN Catch
    on every state that could fail upstream."""
    release_lease = daily_incremental_definition["States"]["ReleaseLease"]
    assert release_lease["Catch"] == [
        {"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "ReleaseLeaseFailedNonFatal"}
    ]
    fallback = daily_incremental_definition["States"]["ReleaseLeaseFailedNonFatal"]
    assert fallback["Type"] == "Pass"
    assert fallback["End"] is True


# ---------------------------------------------------------------------------
# sec_fetch_active cross-command lease (release-readiness ticket 84):
# AcquireSecFetchLease -> ReadSecFetchLeaseResult -> SecFetchLeaseAcquiredCheck
# -> {<fetch-phase-start> | SecFetchDeferred}, and ReleaseSecFetchLease
# before Mastering. Independent of the existing identity-refresh lease above.
# ---------------------------------------------------------------------------


def test_daily_incremental_acquires_sec_fetch_lease_before_refresh_mode(
    daily_incremental_definition,
) -> None:
    """The lease must be acquired after ApplyEffectiveRefreshMode (so the
    lease-resolved refresh_mode is already settled) but before RefreshMode's
    Choice dispatches into any SEC-calling stage."""
    states = daily_incremental_definition["States"]
    assert states["ApplyEffectiveRefreshMode"]["Next"] == "AcquireSecFetchLease"

    acquire = states["AcquireSecFetchLease"]
    assert acquire["ResultPath"] is None
    assert acquire["Next"] == "ReadSecFetchLeaseResult"

    check = states["SecFetchLeaseAcquiredCheck"]
    assert check["Choices"][0]["Next"] == "RefreshMode"


def test_daily_incremental_releases_sec_fetch_lease_before_mdm_run(
    daily_incremental_definition,
) -> None:
    """Every path into Mastering that used to go there directly from the ADV/
    firm-roster fetch chain (the happy path and every Catch fallthrough)
    must now release the lease first -- a failure partway through the
    fetch-heavy span must not leave sec_fetch_active wedged for 16h."""
    states = daily_incremental_definition["States"]
    assert states["IngestFirmRosterSources"]["Next"] == "ReleaseSecFetchLease"

    for catching_state in (
        "FetchAdvBulk",
        "FetchAdvBulkForced",
        "IngestAdvBulkSources",
        "FetchFirmRoster",
        "FetchFirmRosterForced",
        "IngestFirmRosterSources",
    ):
        assert states[catching_state]["Catch"] == [
            {"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "ReleaseSecFetchLease"}
        ]

    release = states["ReleaseSecFetchLease"]
    cmd = release["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "release-sec-fetch-lease" in cmd
    assert release["Next"] == "RunMdmChain"
    assert release["Catch"] == [
        {"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "ReleaseSecFetchLeaseFailedNonFatal"}
    ]

    fallback = states["ReleaseSecFetchLeaseFailedNonFatal"]
    assert fallback["Next"] == "RunMdmChain"


def test_daily_incremental_previously_uncaught_states_release_lease_on_failure(
    daily_incremental_definition,
) -> None:
    """release-readiness ticket 86: FindCompaniesWithNewFilings/
    ComputeIdentityBackstopUniverse/CaptureCompanyIdentityBatches/
    PublishCompanyIdentityUpdates/CaptureAndVerifyNewFilings had no Catch at all -- a real
    failure in any of them wedged sec_fetch_active for the full 16h
    stale-reclaim window. Deliberately excludes FetchAdvBulk/
    IngestFirmRosterSources etc., which already had their own Catch
    (adv_bulk_fetch_catch, unchanged by this ticket) before this fix."""
    states = daily_incremental_definition["States"]
    expected_catch = [
        {"ErrorEquals": ["States.ALL"], "ResultPath": "$.sec_fetch_task_error", "Next": "ReleaseSecFetchLeaseAfterFailure"}
    ]
    for previously_uncaught_state in (
        "FindCompaniesWithNewFilings",
        "ComputeIdentityBackstopUniverse",
        "CaptureCompanyIdentityBatches",
        "PublishCompanyIdentityUpdates",
        "CaptureAndVerifyNewFilings",
    ):
        assert states[previously_uncaught_state]["Catch"] == expected_catch

    release_after_failure = states["ReleaseSecFetchLeaseAfterFailure"]
    assert release_after_failure["Next"] == "SecFetchTaskFailed"
    assert release_after_failure["Catch"] == [
        {"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "SecFetchTaskFailed"}
    ]
    assert states["SecFetchTaskFailed"]["Type"] == "Fail"


def test_sec_fetch_lease_read_result_key_matches_the_real_path_resolver(
    daily_incremental_definition,
) -> None:
    """Mirrors test_read_lease_result_key_matches_the_real_path_resolver for
    the identity-refresh lease -- the hand-typed S3 key in
    ReadSecFetchLeaseResult must tie to sec_fetch_lease_path()'s real
    template, or a future .properties change silently makes
    ReadSecFetchLeaseResult (which has no Catch, deliberately) hard-fail
    every SEC-fetching command's execution instead of failing this test."""
    from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver

    relative_template = default_path_resolver().sec_fetch_lease_path("RUNID_PLACEHOLDER").replace(
        "RUNID_PLACEHOLDER", "{}"
    )
    expected_key_expr = (
        f"States.Format('warehouse/bronze/{relative_template}', $$.Execution.Name)"
    )
    key_expr = daily_incremental_definition["States"]["ReadSecFetchLeaseResult"]["Parameters"]["Key.$"]
    assert key_expr == expected_key_expr


def test_daily_incremental_has_both_leases_independently(daily_incremental_definition) -> None:
    """The pre-existing identity-refresh lease (AcquireLease/ReleaseLease,
    spanning the whole run) and the new sec_fetch_active lease
    (AcquireSecFetchLease/ReleaseSecFetchLease, spanning only the SEC/IAPD-
    fetching sub-span) must coexist as two distinct, independently-wired
    lease pairs -- not merged or one replacing the other."""
    states = daily_incremental_definition["States"]
    for name in (
        "AcquireLease", "ReleaseLease", "ReleaseLeaseFailedNonFatal",
        "AcquireSecFetchLease", "ReleaseSecFetchLease", "ReleaseSecFetchLeaseFailedNonFatal",
    ):
        assert name in states

    acquire_lease_cmd = states["AcquireLease"]["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    acquire_sec_fetch_cmd = states["AcquireSecFetchLease"]["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "acquire-identity-refresh-lease" in acquire_lease_cmd
    assert "acquire-sec-fetch-lease" in acquire_sec_fetch_cmd

    # GoldRefresh still routes to the identity-refresh ReleaseLease at the
    # very end of the run -- sec_fetch_active already released much earlier,
    # right before Mastering.
    assert states["FactPublishtoGold"]["Next"] == "ReleaseLease"


def test_sec_fetch_deferred_releases_the_already_acquired_identity_refresh_lease(
    daily_incremental_definition,
) -> None:
    """Regression guard for a lease-leak found live 2026-09-03: by the time
    AcquireSecFetchLease ever runs, AcquireLease (the identity-refresh
    lease, spanning the whole run) has ALWAYS already succeeded --
    AcquireSecFetchLease's only inbound edge is ApplyEffectiveRefreshMode,
    itself only reachable via LeaseAcquiredCheck's lease_acquired=True
    branch. If the sec_fetch_active lease is busy and this run gets
    deferred, it must release the identity-refresh lease it's already
    holding before terminating -- otherwise that lease stays held under
    this (now-terminated) execution's own run_id until the 20h stale-lease
    reclaim, silently blocking every subsequent daily_incremental
    execution's own AcquireLease. Confirmed live:
    daily-incremental-claimfix-verify2-1788478059 got sec-fetch-deferred
    and stranded the identity-refresh lease exactly this way.

    Walks the real generated graph forward from
    SecFetchLeaseAcquiredCheck's Default (busy) branch, following each
    state's single Next pointer, until it reaches either a state whose
    command contains "release-identity-refresh-lease" (pass) or a
    terminal End:true state with no such release anywhere on the path
    (fail)."""
    states = daily_incremental_definition["States"]
    current = states["SecFetchLeaseAcquiredCheck"]["Default"]
    visited: list[str] = []
    released = False
    for _ in range(len(states) + 1):  # bounded walk; a real cycle would be a separate bug
        visited.append(current)
        state = states[current]
        cmd = json.dumps(state.get("Parameters", {}))
        if "release-identity-refresh-lease" in cmd:
            released = True
            break
        if state.get("End"):
            break
        nxt = state.get("Next")
        if nxt is None:
            break
        current = nxt

    assert released, (
        f"SecFetchDeferred path ({' -> '.join(visited)}) terminates without "
        "releasing the already-acquired identity-refresh lease"
    )
