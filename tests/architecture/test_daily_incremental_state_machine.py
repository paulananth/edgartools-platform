"""Structural checks on the generated daily_incremental Step Functions definition.

Covers the Company Identity Pipeline wayfinder map's ticket 06 (see
.scratch/company-master-pipeline/issues/06-daily-mode-state-machine-shape.md):

- daily_incremental is restructured with a new Stage0CompanyIdentity phase,
  reusing ticket 05's exact windowed capture shape (ComputeWindows + a
  strict, MaxConcurrency=1 Map), ahead of the existing RunWarehouseTask/MDM
  chain.

(bootstrap, the other former caller of write_warehouse_mdm_gold_definition,
was explicitly untouched by this restructure at the time -- and was later
retired entirely by state-machine-consolidation ticket 06. Its regression
tests here were removed alongside it.)

These tests generate the real JSON by sourcing the actual bash function (no
duplicated/hand-maintained copy of the state machine shape) and asserting on
the output, mirroring test_load_history_state_machine.py's approach.
Network-free: no AWS calls, only local JSON generation via python3
subprocesses that the deploy script itself launches.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"

_START_MARKER = "write_warehouse_mdm_gold_definition() {\n"
_END_MARKER = "\nPY\n}\n"

# write_warehouse_mdm_gold_definition calls command_task_profile()
# internally (task-profile-consolidation ticket 02) to resolve
# RunWarehouseTask's profile -- extracted and sourced alongside it below.
_COMMAND_TASK_PROFILE_START = "command_task_profile() {\n"
_COMMAND_TASK_PROFILE_END = "\n}\n"

# LeaseAcquiredCheck inverts this file's usual Choice convention (Default is
# the fail-closed Deferred path, not the happy path) -- trace helpers must be
# told to prefer the explicit lease_acquired=True branch when tracing the
# successful/main flow. See _linear_order_with_choice's docstring.
_LEASE_ACQUIRED_PREFER = {
    "ValidateForceInput": "ForceDefault",
    "LeaseAcquiredCheck": "ApplyEffectiveRefreshMode",
    # SecFetchLeaseAcquiredCheck (release-readiness ticket 84) inverts the
    # same way LeaseAcquiredCheck does -- Default is the fail-closed
    # deferred path, not the happy path.
    "SecFetchLeaseAcquiredCheck": "RefreshMode",
    "ForceCheck": "FetchAdvBulk",
    "FirmRosterForceCheck": "FetchFirmRoster",
}

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def _choice_next(state: dict, execution_input: dict) -> str:
    """Evaluate the root-field Choice operators used by the generated contract."""
    for choice in state["Choices"]:
        key = choice["Variable"].removeprefix("$.")
        present = key in execution_input
        value = execution_input.get(key)
        if "IsPresent" in choice and present is choice["IsPresent"]:
            return choice["Next"]
        if (
            "IsBoolean" in choice
            and present
            and isinstance(value, bool)
            and choice["IsBoolean"] is True
        ):
            return choice["Next"]
        if (
            "BooleanEquals" in choice
            and isinstance(value, bool)
            and value is choice["BooleanEquals"]
        ):
            return choice["Next"]
    return state["Default"]


def _extract_function_source() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index(_START_MARKER)
    end = text.index(_END_MARKER, start) + len(_END_MARKER)
    return text[start:end]


def _extract_command_task_profile_source() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index(_COMMAND_TASK_PROFILE_START)
    end = text.index(_COMMAND_TASK_PROFILE_END, start) + len(_COMMAND_TASK_PROFILE_END)
    return text[start:end]


def _generate(workflow_name: str) -> dict:
    fn_source = _extract_function_source()
    command_task_profile_source = _extract_command_task_profile_source()

    tmp_root = REPO_ROOT / ".pytest_cache" / "daily_incremental_sm_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        fn_file = tmp_path / "warehouse_mdm_gold_fn.sh"
        fn_file.write_text(fn_source, encoding="utf-8")
        command_task_profile_file = tmp_path / "command_task_profile_fn.sh"
        command_task_profile_file.write_text(command_task_profile_source, encoding="utf-8")
        out_file = tmp_path / f"{workflow_name}.json"

        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'fail() { echo "ERROR: $*" >&2; exit 1; }\n'
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            'BRONZE_BUCKET_NAME="fake-bronze-bucket"\n'
            "PUBLIC_SUBNET_IDS_JSON='[\"subnet-aaaa\",\"subnet-bbbb\"]'\n"
            "SECURITY_GROUP_IDS_JSON='[\"sg-cccc\"]'\n"
            f'SCRIPT_DIR="{(REPO_ROOT / "infra" / "scripts").as_posix()}"\n'
            f'source "{command_task_profile_file.as_posix()}"\n'
            f'source "{fn_file.as_posix()}"\n'
            f'write_warehouse_mdm_gold_definition "{out_file.as_posix()}" '
            '"arn:wh-medium" "arn:wh-large" '
            f'"{workflow_name}" "fake-bronze-bucket" "arn:aws:sns:us-east-1:000000000000:fake-alerts" '
            '"arn:mdm-machine"\n',
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
def daily_definition() -> dict:
    return _generate("daily_incremental")


def _command_of_state(state: dict) -> str:
    if state.get("Type") == "Map":
        proc_states = state["ItemProcessor"]["States"]
        return " ".join(_command_of_state(s) for s in proc_states.values())
    containers = state.get("Parameters", {}).get("Overrides", {}).get("ContainerOverrides", [])
    return containers[0]["Command.$"] if containers else ""


def _command_of(definition: dict, state_name: str) -> str:
    return _command_of_state(definition["States"][state_name])


def _linear_order(definition: dict) -> list[str]:
    states = definition["States"]

    def next_of(state: dict) -> str | None:
        if "Next" in state:
            return state["Next"]
        return None

    order: list[str] = []
    seen: set[str] = set()
    name = definition["StartAt"]
    while name and name not in seen:
        seen.add(name)
        order.append(name)
        name = next_of(states[name])
    return order


# -- structural integrity ----------------------------------------------------


def test_generates_valid_json_with_no_dangling_references(daily_definition: dict) -> None:
    def check(states: dict, start_at: str, label: str) -> None:
        assert start_at in states, f"{label}: StartAt not defined"
        for name, state in states.items():
            nxt = state.get("Next")
            if nxt is not None:
                assert nxt in states, f"{label}.{name}: Next={nxt!r} undefined"
            for catch in state.get("Catch", []):
                cnxt = catch.get("Next")
                if cnxt is not None:
                    assert cnxt in states, f"{label}.{name}: Catch Next={cnxt!r} undefined"
            if state.get("Type") == "Map":
                proc = state["ItemProcessor"]
                check(proc["States"], proc["StartAt"], f"{label}.{name}(Map)")

    check(daily_definition["States"], daily_definition["StartAt"], "top")


# -- ticket 06: Stage0CompanyIdentity woven into daily_incremental -----------


def test_daily_incremental_validates_force_before_refresh_mode(daily_definition: dict) -> None:
    """Restructured by release-readiness ticket 45/49 (bounded Daily Identity
    Refresh): daily_incremental now decides refresh_mode before choosing
    between the daily impacted-company path and complete company backstop --
    see tests/architecture/test_daily_identity_refresh_state_machine.py for
    the full shape of both branches."""
    states = daily_definition["States"]
    assert daily_definition["StartAt"] == "ValidateForceInput"
    validation = states["ValidateForceInput"]
    assert _choice_next(validation, {}) == "ForceDefault"
    assert _choice_next(validation, {"force": False}) == "RefreshModeCheck"
    assert _choice_next(validation, {"force": True}) == "RefreshModeCheck"
    assert _choice_next(validation, {"force": "true"}) == "InvalidForceInput"

    assert states["ForceDefault"] == {
        "Type": "Pass",
        "Comment": "Normalize an omitted operator force input to false.",
        "Result": False,
        "ResultPath": "$.force",
        "Next": "RefreshModeCheck",
    }
    assert states["InvalidForceInput"]["Type"] == "Fail"
    assert states["InvalidForceInput"]["Error"] == "InvalidForceInput"


def test_daily_incremental_default_path_reaches_run_warehouse_task_via_bounded_stage0(
    daily_definition: dict,
) -> None:
    """The default (no refresh_mode input) path no longer runs the
    full-universe ComputeWindows/Stage0CompanyIdentity pair -- it runs the
    bounded ComputeIdentityRefreshWindow/ResolveCompanyIdentityBounded pair
    instead (ticket 45/49). Backstop uses the same explicit-CIK stage with a
    complete company-eligible input."""
    order = _linear_order_with_choice(daily_definition, prefer=_LEASE_ACQUIRED_PREFER)
    assert "ComputeIdentityRefreshWindow" in order
    assert "ResolveCompanyIdentityBounded" in order
    assert "RunWarehouseTask" in order
    assert order.index("ComputeIdentityRefreshWindow") < order.index("ResolveCompanyIdentityBounded")
    assert order.index("ResolveCompanyIdentityBounded") < order.index("RunWarehouseTask")


def test_daily_incremental_stage0_company_identity_command_shape(daily_definition: dict) -> None:
    cmd = _command_of(daily_definition, "ResolveCompanyIdentityBounded")
    assert "'bootstrap-fundamentals'" in cmd
    assert "'--mode', 'company-identity'" in cmd
    assert "'--cik-list'" in cmd
    assert "'--cik-offset'" not in cmd
    assert "'--cik-limit'" not in cmd


def test_daily_incremental_stage0_company_identity_is_strict_not_lenient(
    daily_definition: dict,
) -> None:
    """release-readiness ticket 86 added a Catch here (a real failure
    previously wedged sec_fetch_active for 16h instead of releasing it),
    but strictness is preserved -- the Catch releases the lease and then
    still fails the execution (SecFetchTaskFailed, a Fail state), it does
    not route to ReduceIdentityRefresh or any other "proceed anyway" state."""
    state = daily_definition["States"]["ResolveCompanyIdentityBounded"]
    assert state["Type"] == "Map"
    assert state["MaxConcurrency"] == 1
    assert state["ToleratedFailurePercentage"] == 0
    catch = state["Catch"]
    assert len(catch) == 1
    assert catch[0]["ErrorEquals"] == ["States.ALL"]
    assert catch[0]["Next"] == "ReleaseSecFetchLeaseAfterFailure"
    assert daily_definition["States"]["ReleaseSecFetchLeaseAfterFailure"]["Next"] == "SecFetchTaskFailed"
    assert daily_definition["States"]["SecFetchTaskFailed"]["Type"] == "Fail"


def test_daily_incremental_stage0_company_identity_uses_distributed_mode(
    daily_definition: dict,
) -> None:
    """AWS Step Functions rejects ItemReader on an INLINE Map -- must match
    load_history's already-working DISTRIBUTED pattern (fix-pipelines 06-03)."""
    state = daily_definition["States"]["ResolveCompanyIdentityBounded"]
    assert "ItemReader" in state
    assert state["ItemProcessor"]["ProcessorConfig"]["Mode"] == "DISTRIBUTED"
    assert state["ItemProcessor"]["ProcessorConfig"]["ExecutionType"] == "STANDARD"


def test_daily_incremental_no_seed_universe(daily_definition: dict) -> None:
    """daily_incremental deliberately skips seed-universe/MdmSeedUniverse --
    it processes the already-tracked universe for daily updates, not
    newly-discovered CIKs. This must remain true after the restructure."""
    assert "SeedUniverse" not in daily_definition["States"]
    assert "MdmSeedUniverse" not in daily_definition["States"]


# Mastering itself (--entity-type all, no dedicated --entity-type company
# call -- run_all() already calls run_companies() as part of its sweep)
# no longer exists at this level (state-machine-consolidation wayfinder
# map, ticket 07) -- it moved into the single MDM machine, invoked here as
# one RunMdmChain nested execution. Covered by
# tests/architecture/test_mdm_state_machine.py against the real generated
# MDM machine instead.


def test_daily_filing_ingestion_does_not_inherit_identity_cik_batches(
    daily_definition: dict,
) -> None:
    """The company filter scopes Stage 0 only. RunWarehouseTask retains the
    ordinary daily-incremental filing contract and receives no identity batch."""
    cmd = _command_of(daily_definition, "RunWarehouseTask")
    assert "'daily-incremental'" in cmd
    assert "'--cik-list'" not in cmd
    assert "$.cik_list" not in cmd


def test_scheduled_daily_filing_ingestion_forces_exact_seven_day_index_boundary(
    daily_definition: dict,
) -> None:
    cmd = _command_of(daily_definition, "RunWarehouseTask")
    assert "'--recurring-index-lookback-days', '7'" in cmd


def test_daily_incremental_no_dedicated_gold_refresh_for_company_identity(
    daily_definition: dict,
) -> None:
    """Exactly one FactPublishtoGold state (renamed from GoldRefresh --
    state-machine-consolidation wayfinder map, ticket 07) -- company-identity
    feeds the existing single gold-refresh, no dedicated refresh added."""
    gold_refresh_states = [name for name in daily_definition["States"] if "Gold" in name]
    assert gold_refresh_states == ["FactPublishtoGold"]


# -- ADV fetch pipeline wiring spec (.scratch/adv-fetch-pipeline-wiring, ticket 02):
# AdvBulkFetch stage between RunWarehouseTask and Mastering -------------------------


def _linear_order_with_choice(definition: dict, prefer: dict[str, str] | None = None) -> list[str]:
    """Like _linear_order but also follows Choice states, needed once
    DatasetPeriodCheck/ForceCheck/LeaseAcquiredCheck (Choice states) sit
    between RunWarehouseTask and Mastering -- the module-level _linear_order
    only follows plain "Next", matching this file's original no-Choice-states
    shape.

    For most Choice states here, Default IS the main/happy path (the
    Choices branch is the override) -- so Default-first is the right
    default trace. LeaseAcquiredCheck inverts this deliberately for safety
    (Default = Deferred, a fail-closed disposition for anything that isn't
    exactly lease_acquired=True) -- pass `prefer={"LeaseAcquiredCheck":
    "ApplyEffectiveRefreshMode"}` to trace the happy path through it
    instead (ApplyEffectiveRefreshMode itself has a plain "Next", so the
    trace continues on to RefreshMode from there without needing its own
    prefer entry)."""
    states = definition["States"]
    prefer = prefer or {}

    def next_of(name: str, state: dict) -> str | None:
        if "Next" in state:
            return state["Next"]
        if name in prefer:
            return prefer[name]
        if state.get("Type") == "Choice":
            return state.get("Default") or state["Choices"][0]["Next"]
        return None

    order: list[str] = []
    seen: set[str] = set()
    name = definition["StartAt"]
    while name and name not in seen:
        seen.add(name)
        order.append(name)
        name = next_of(name, states[name])
    return order


def test_fetch_adv_bulk_stage_runs_after_run_warehouse_task_before_mdm_run(
    daily_definition: dict,
) -> None:
    order = _linear_order_with_choice(daily_definition, prefer=_LEASE_ACQUIRED_PREFER)
    assert "RunWarehouseTask" in order
    assert "FetchAdvBulk" in order
    assert "IngestAdvBulkSources" in order
    assert "RunMdmChain" in order
    assert order.index("RunWarehouseTask") < order.index("FetchAdvBulk")
    assert order.index("FetchAdvBulk") < order.index("IngestAdvBulkSources")
    assert order.index("IngestAdvBulkSources") < order.index("RunMdmChain")


def test_fetch_adv_bulk_command_shape_with_no_sm_input_overrides(daily_definition: dict) -> None:
    cmd = _command_of(daily_definition, "FetchAdvBulk")
    assert "'fetch-adv-bulk'" in cmd
    assert "'--dataset-period'" in cmd
    assert "'--force'" not in cmd
    assert "'--run-id'" in cmd


def test_dataset_period_check_and_default_precede_force_check(daily_definition: dict) -> None:
    states = daily_definition["States"]
    check = states["DatasetPeriodCheck"]
    assert check["Type"] == "Choice"
    assert check["Choices"][0]["Variable"] == "$.dataset_period"
    assert check["Choices"][0]["IsPresent"] is True
    assert check["Choices"][0]["Next"] == "ForceCheck"
    assert check["Default"] == "DatasetPeriodDefault"

    default_state = states["DatasetPeriodDefault"]
    assert default_state["Type"] == "Pass"
    assert default_state["Result"] == ""
    assert default_state["ResultPath"] == "$.dataset_period"
    assert default_state["Next"] == "ForceCheck"


def test_force_check_routes_to_two_distinct_fetch_adv_bulk_command_shapes(
    daily_definition: dict,
) -> None:
    states = daily_definition["States"]
    force_check = states["ForceCheck"]
    assert force_check["Type"] == "Choice"
    assert _choice_next(force_check, {}) == "FetchAdvBulk"
    assert _choice_next(force_check, {"force": False}) == "FetchAdvBulk"
    assert _choice_next(force_check, {"force": True}) == "FetchAdvBulkForced"
    assert _choice_next(force_check, {"force": "true"}) == "InvalidForceInput"

    no_force_cmd = _command_of(daily_definition, "FetchAdvBulk")
    forced_cmd = _command_of(daily_definition, "FetchAdvBulkForced")
    assert "'--force'" not in no_force_cmd
    assert "'--force'" in forced_cmd
    assert no_force_cmd.replace(", '--force'", "") == forced_cmd.replace(", '--force'", "")

    assert states["FetchAdvBulk"]["Next"] == "IngestAdvBulkSources"
    assert states["FetchAdvBulkForced"]["Next"] == "IngestAdvBulkSources"


def test_ingest_adv_bulk_sources_references_fetch_adv_bulk_manifest_path(
    daily_definition: dict,
) -> None:
    cmd = _command_of(daily_definition, "IngestAdvBulkSources")
    assert "'ingest-relationship-sources'" in cmd
    assert "'--source-manifest'" in cmd
    assert "runs/fetch-adv-bulk/" in cmd
    assert "source_manifest.json" in cmd
    assert "$$.Execution.Name" in cmd


def test_fetch_adv_bulk_and_ingest_adv_bulk_sources_catch_falls_through_to_mdm_run(
    daily_definition: dict,
) -> None:
    """Catch falls through to ReleaseSecFetchLease, not Mastering directly
    (release-readiness ticket 84) -- these fetch stages are still inside the
    sec_fetch_active fetch-heavy span, so a failure must still release the
    lease before proceeding to MDM."""
    for state_name in ("FetchAdvBulk", "FetchAdvBulkForced", "IngestAdvBulkSources"):
        state = daily_definition["States"][state_name]
        assert state.get("Catch") == [
            {"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "ReleaseSecFetchLease"}
        ], f"{state_name} missing lenient Catch-to-ReleaseSecFetchLease"
    assert daily_definition["States"]["ReleaseSecFetchLease"]["Next"] == "RunMdmChain"


def test_fetch_and_ingest_adv_bulk_states_preserve_sm_input_via_result_path_null(
    daily_definition: dict,
) -> None:
    """Regression guard for the D-15 bug class (see load_history's identical
    test): an ecs:runTask.sync Task without ResultPath=null replaces $ entirely
    with its own result, destroying $.dataset_period/$.force downstream."""
    for state_name in ("FetchAdvBulk", "FetchAdvBulkForced", "IngestAdvBulkSources"):
        assert daily_definition["States"][state_name]["ResultPath"] is None, (
            f"{state_name} must set ResultPath=null to preserve $ into the next state"
        )


def test_daily_tasks_before_force_check_preserve_operator_input(daily_definition: dict) -> None:
    for state_name in (
        "ComputeIdentityRefreshWindow",
        "ComputeIdentityBackstopUniverse",
        "RunWarehouseTask",
    ):
        assert daily_definition["States"][state_name]["ResultPath"] is None, (
            f"{state_name} must preserve normalized operator input through ForceCheck"
        )


def test_firm_roster_stage_runs_after_ingest_adv_bulk_sources_before_mdm_run(
    daily_definition: dict,
) -> None:
    order = _linear_order_with_choice(daily_definition, prefer=_LEASE_ACQUIRED_PREFER)
    assert "IngestAdvBulkSources" in order
    assert "FetchFirmRoster" in order
    assert "IngestFirmRosterSources" in order
    assert "RunMdmChain" in order
    assert order.index("IngestAdvBulkSources") < order.index("FetchFirmRoster")
    assert order.index("FetchFirmRoster") < order.index("IngestFirmRosterSources")
    assert order.index("IngestFirmRosterSources") < order.index("RunMdmChain")


def test_ingest_adv_bulk_sources_routes_into_firm_roster_force_check_not_around_it(
    daily_definition: dict,
) -> None:
    assert daily_definition["States"]["IngestAdvBulkSources"]["Next"] == "FirmRosterForceCheck"


def test_firm_roster_force_check_routes_to_two_distinct_fetch_firm_roster_command_shapes(
    daily_definition: dict,
) -> None:
    states = daily_definition["States"]
    force_check = states["FirmRosterForceCheck"]
    assert force_check["Type"] == "Choice"
    assert _choice_next(force_check, {}) == "FetchFirmRoster"
    assert _choice_next(force_check, {"force": False}) == "FetchFirmRoster"
    assert _choice_next(force_check, {"force": True}) == "FetchFirmRosterForced"
    assert _choice_next(force_check, {"force": "true"}) == "InvalidForceInput"

    no_force_cmd = _command_of(daily_definition, "FetchFirmRoster")
    forced_cmd = _command_of(daily_definition, "FetchFirmRosterForced")
    assert "'fetch-firm-roster'" in no_force_cmd
    assert "'--force'" not in no_force_cmd
    assert "'--force'" in forced_cmd
    assert no_force_cmd.replace(", '--force'", "") == forced_cmd.replace(", '--force'", "")

    assert states["FetchFirmRoster"]["Next"] == "IngestFirmRosterSources"
    assert states["FetchFirmRosterForced"]["Next"] == "IngestFirmRosterSources"


def test_ingest_firm_roster_sources_references_fetch_firm_roster_manifest_path(
    daily_definition: dict,
) -> None:
    cmd = _command_of(daily_definition, "IngestFirmRosterSources")
    assert "'ingest-relationship-sources'" in cmd
    assert "'--source-manifest'" in cmd
    assert "runs/fetch-firm-roster/" in cmd
    assert "source_manifest.json" in cmd
    assert "$$.Execution.Name" in cmd


def test_fetch_and_ingest_firm_roster_catch_falls_through_to_mdm_run(
    daily_definition: dict,
) -> None:
    """Catch falls through to ReleaseSecFetchLease, not Mastering directly
    (release-readiness ticket 84) -- see the identical ADV-fetch test above."""
    for state_name in ("FetchFirmRoster", "FetchFirmRosterForced", "IngestFirmRosterSources"):
        state = daily_definition["States"][state_name]
        assert state.get("Catch") == [
            {"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "ReleaseSecFetchLease"}
        ], f"{state_name} missing lenient Catch-to-ReleaseSecFetchLease"
    assert daily_definition["States"]["ReleaseSecFetchLease"]["Next"] == "RunMdmChain"



def test_fetch_and_ingest_firm_roster_states_preserve_sm_input_via_result_path_null(
    daily_definition: dict,
) -> None:
    for state_name in ("FetchFirmRoster", "FetchFirmRosterForced", "IngestFirmRosterSources"):
        assert daily_definition["States"][state_name]["ResultPath"] is None, (
            f"{state_name} must set ResultPath=null to preserve $ into the next state"
        )


# -- mdm-ahead-of-silver map, Phase B wiring: BackfillMdmEntityIds sweep -----
# Originally parametrized over both daily_definition and bootstrap_definition
# (both shared write_warehouse_mdm_gold_definition's Mastering -> ... ->
# Infer Relationships chain); bootstrap was retired by state-machine-consolidation
# ticket 06, so these now cover daily_definition only.
#
# Ticket 06 (.scratch/mdm-ahead-of-silver/issues/06-narrow-backfill-storage-target.md)
# simplified this from an earlier lease-guarded shape (AcquireEntityBackfillLease/
# ReadEntityBackfillLeaseResult/EntityBackfillLeaseAcquiredCheck/
# ReleaseEntityBackfillLease*) once the sweep became Snowflake-only: no DuckDB
# shard is read or written anymore, so there's nothing left for the
# sec_fetch_active lease to protect. That shape and these tests were removed,
# not left asserting a dead state -- see commit history for the prior version
# if the lease-guarded design is ever needed again.


# Mastering -> BackfillMdmEntityIds (renamed BackpropagateIdsToSilver) ->
# Infer Relationships no longer exist at this level (state-machine-
# consolidation wayfinder map, ticket 07) -- they moved into the single MDM
# machine, invoked here as one RunMdmChain nested execution. Also widened
# from daily_incremental-only to every MDM-machine caller per this
# implementation's own follow-up decision. Covered by
# tests/architecture/test_mdm_state_machine.py against the real generated
# MDM machine instead (test_tail_order_is_mastering_through_reconcile,
# test_backpropagate_ids_to_silver_uses_backfill_mdm_entity_ids_command,
# test_backpropagate_ids_to_silver_failure_is_non_fatal,
# test_backpropagate_ids_to_silver_uses_the_warehouse_medium_profile).


def test_no_entity_backfill_lease_states_remain(daily_definition: dict) -> None:
    """The lease-guarded shape ticket 06 superseded must not linger as dead
    states in the generated definition."""
    states = daily_definition["States"]
    for name in (
        "AcquireEntityBackfillLease",
        "ReadEntityBackfillLeaseResult",
        "EntityBackfillLeaseAcquiredCheck",
        "ReleaseEntityBackfillLease",
        "ReleaseEntityBackfillLeaseFailedNonFatal",
        "ReleaseEntityBackfillLeaseAfterFailure",
    ):
        assert name not in states


def test_sec_fetch_lease_still_releases_into_mdm_run_unaffected(daily_definition: dict) -> None:
    """The main sec_fetch_active span (build_sec_fetch_lease_states, guarding
    SeedUniverse/RunWarehouseTask) is untouched by the entity-backfill sweep
    simplification -- it still releases right before Mastering."""
    states = daily_definition["States"]
    assert states["ReleaseSecFetchLease"]["Next"] == "RunMdmChain"
    assert states["AcquireSecFetchLease"]["Next"] == "ReadSecFetchLeaseResult"
