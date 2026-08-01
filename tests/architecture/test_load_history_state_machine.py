"""Structural checks on the generated load_history Step Functions definition.

Covers the data-architecture review fixes (see
.planning/workstreams/claude-data-architecture-fixes/CLAUDE-INSTRUCTIONS.md):

- Issue 1/3: Branch B fundamentals must run AFTER Branch A completes because
  Branch A and Branch B now share the same SEC silver DuckDB artifact.
- Issue 2: MdmSeedUniverse (mdm seed-universe) must run before ComputeWindows,
  and bootstrap-next must pass the same tracking-status filter compute-windows
  uses (not its own single-status CLI default).
- Issue 3: mdm export must precede mdm sync-graph.
- Issue 4: a thirteenf stage must exist in the generated state machine.

These tests generate the real JSON by sourcing the actual bash function (no
duplicated/hand-maintained copy of the state machine shape) and asserting on
the output, so they catch drift the same way "inspect the generated JSON
before deployment" (CLAUDE-INSTRUCTIONS.md) asks for, just automated. Network-
free: no AWS calls, only local JSON generation via python3 subprocesses that
the deploy script itself launches.
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

_START_MARKER = "write_load_history_definition() {\n"
_END_MARKER = "\nPY\n}\n"

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


@pytest.fixture(scope="module")
def definition() -> dict:
    """Generate load_history's Step Functions JSON with dummy ARNs (no AWS calls)."""
    fn_source = _extract_function_source()

    # dir= is repo-local (under the already-gitignored .pytest_cache/), not the
    # system temp dir: some sandboxed dev environments allow bash to read/exec
    # files under the project tree but not under the OS temp directory.
    tmp_root = REPO_ROOT / ".pytest_cache" / "load_history_sm_test"
    tmp_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        fn_file = tmp_path / "load_history_fn.sh"
        fn_file.write_text(fn_source, encoding="utf-8")
        out_file = tmp_path / "load_history.json"

        # Git Bash/MSYS mangles backslash-separated Windows paths passed as argv
        # (it treats backslash as an escape character), so use forward-slash
        # paths for everything handed to bash — valid on Windows too.
        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            'BRONZE_BUCKET_NAME="fake-bronze-bucket"\n'
            "PUBLIC_SUBNET_IDS_JSON='[\"subnet-aaaa\",\"subnet-bbbb\"]'\n"
            "SECURITY_GROUP_IDS_JSON='[\"sg-cccc\"]'\n"
            "MDM_RUN_LIMIT=100\n"
            "MDM_GRAPH_LIMIT=200\n"
            'MDM_SEED_UNIVERSE_TRACKING_STATUS="bootstrap_pending"\n'
            f'source "{fn_file.as_posix()}"\n'
            f'write_load_history_definition "{out_file.as_posix()}" '
            '"arn:wh-small" "arn:wh-medium" "arn:mdm-small" "arn:mdm-medium" "arn:wh-large"\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            ["bash", driver.as_posix()], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise AssertionError(
                f"load_history definition generation failed after retries:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        return json.loads(out_file.read_text(encoding="utf-8"))


def _command_of(definition: dict, state_name: str) -> str:
    state = definition["States"][state_name]
    return _command_of_state(state)


def _command_of_state(state: dict) -> str:
    if state.get("Type") == "Map":
        proc_states = state["ItemProcessor"]["States"]
        return " ".join(_command_of_state(s) for s in proc_states.values())
    containers = state.get("Parameters", {}).get("Overrides", {}).get("ContainerOverrides", [])
    return containers[0]["Command.$"] if containers else ""


def _linear_order(definition: dict) -> list[str]:
    """Walk Next/Choice.Default from StartAt. Every branch of the one Choice
    state (WindowSizeCheck) converges on ComputeWindows within one hop, so
    following Default is sufficient to observe top-level ordering."""
    states = definition["States"]

    def next_of(state: dict) -> str | None:
        if "Next" in state:
            return state["Next"]
        if state.get("Type") == "Choice":
            return state.get("Default") or state["Choices"][0]["Next"]
        return None

    order: list[str] = []
    seen: set[str] = set()
    name = definition["StartAt"]
    preferred_choices = {
        "ValidateForceInput": "ForceDefault",
        "ForceCheck": "FetchAdvBulk",
        "FirmRosterForceCheck": "FetchFirmRoster",
    }
    while name and name not in seen:
        seen.add(name)
        order.append(name)
        name = preferred_choices.get(name) or next_of(states[name])
    return order


# -- structural integrity ----------------------------------------------------


def test_generates_valid_json_with_no_dangling_references(definition: dict) -> None:
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
            if state.get("Type") == "Parallel":
                for i, branch in enumerate(state["Branches"]):
                    check(branch["States"], branch["StartAt"], f"{label}.{name}(Parallel[{i}])")

    check(definition["States"], definition["StartAt"], "top")


def test_load_history_validates_force_before_workload(definition: dict) -> None:
    states = definition["States"]
    assert definition["StartAt"] == "ValidateForceInput"
    validation = states["ValidateForceInput"]
    assert _choice_next(validation, {}) == "ForceDefault"
    assert _choice_next(validation, {"force": False}) == "SeedUniverse"
    assert _choice_next(validation, {"force": True}) == "SeedUniverse"
    assert _choice_next(validation, {"force": 1}) == "InvalidForceInput"

    assert states["ForceDefault"] == {
        "Type": "Pass",
        "Comment": "Normalize an omitted operator force input to false.",
        "Result": False,
        "ResultPath": "$.force",
        "Next": "SeedUniverse",
    }
    assert states["InvalidForceInput"]["Type"] == "Fail"
    assert states["InvalidForceInput"]["Error"] == "InvalidForceInput"


# -- Issue 2: MDM seeding -----------------------------------------------------


def test_mdm_seed_universe_runs_before_compute_windows(definition: dict) -> None:
    order = _linear_order(definition)
    assert "MdmSeedUniverse" in order
    assert "ComputeWindows" in order
    assert order.index("MdmSeedUniverse") < order.index("ComputeWindows")


def test_mdm_seed_universe_calls_mdm_subcommand_not_warehouse_seed_universe(definition: dict) -> None:
    cmd = _command_of(definition, "MdmSeedUniverse")
    assert "'mdm', 'seed-universe'" in cmd


def test_seed_universe_no_longer_claims_mdm_enrollment(definition: dict) -> None:
    """SeedUniverse (warehouse) is bronze-only; MdmSeedUniverse does the MDM
    enrollment. Regression guard for the original doc/comment mismatch."""
    seed_universe_cmd = _command_of(definition, "SeedUniverse")
    assert "'seed-universe'" in seed_universe_cmd
    assert "mdm" not in seed_universe_cmd


def test_bootstrap_next_and_compute_windows_use_the_same_tracking_status_filter(definition: dict) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import (
        LOAD_HISTORY_TRACKING_STATUS_FILTER,
    )

    branch_a_states = definition["States"]["Stage1Parallel"]["Branches"][0]["States"]
    per_window_cmd = _command_of_state(branch_a_states["WindowedBootstrap"])
    assert f"'--tracking-status-filter', '{LOAD_HISTORY_TRACKING_STATUS_FILTER}'" in per_window_cmd


def test_windowed_bootstrap_is_silver_only(definition: dict) -> None:
    branch_a_states = definition["States"]["Stage1Parallel"]["Branches"][0]["States"]
    per_window_cmd = _command_of_state(branch_a_states["WindowedBootstrap"])
    assert "'bootstrap-next'" in per_window_cmd
    assert "'--silver-only'" in per_window_cmd


def test_windowed_bootstrap_projects_artifact_policy_into_each_item(
    definition: dict,
) -> None:
    """The S3 JSONL rows contain only window bounds, while RunWindow also reads
    the execution-scoped artifact policy. The Distributed Map must combine both
    inputs before starting each child execution."""
    branch_a_states = definition["States"]["Stage1Parallel"]["Branches"][0]["States"]
    windowed_bootstrap = branch_a_states["WindowedBootstrap"]

    assert windowed_bootstrap["ItemSelector"] == {
        "window_offset.$": "$$.Map.Item.Value.window_offset",
        "window_limit.$": "$$.Map.Item.Value.window_limit",
        "artifact_policy.$": "$.artifact_policy",
    }


def test_load_history_has_one_final_gold_refresh_after_mdm_verify(definition: dict) -> None:
    gold_commands: list[tuple[str, str]] = []

    def walk(states: dict, label: str) -> None:
        for name, state in states.items():
            command = _command_of_state(state)
            if "'gold-refresh'" in command:
                gold_commands.append((f"{label}.{name}", command))
            if state.get("Type") == "Map":
                processor = state["ItemProcessor"]
                walk(processor["States"], f"{label}.{name}(Map)")
            if state.get("Type") == "Parallel":
                for index, branch in enumerate(state["Branches"]):
                    walk(branch["States"], f"{label}.{name}(Parallel[{index}])")

    walk(definition["States"], "top")
    assert [name for name, _ in gold_commands] == ["top.GoldRefresh"]
    assert definition["States"]["GoldRefresh"]["Parameters"]["TaskDefinition"] == "arn:wh-large"

    order = _linear_order(definition)
    assert order.index("MdmVerify") < order.index("GoldRefresh")


# -- Company Identity Pipeline wayfinder map, ticket 05: Stage0CompanyIdentity ---


def test_stage0_company_identity_runs_after_compute_windows_before_stage1_parallel(
    definition: dict,
) -> None:
    order = _linear_order(definition)
    assert "ComputeWindows" in order
    assert "Stage0CompanyIdentity" in order
    assert "Stage1Parallel" in order
    assert order.index("ComputeWindows") < order.index("Stage0CompanyIdentity")
    assert order.index("Stage0CompanyIdentity") < order.index("Stage1Parallel")


def test_stage0_company_identity_command_shape(definition: dict) -> None:
    cmd = _command_of(definition, "Stage0CompanyIdentity")
    assert "'bootstrap-fundamentals'" in cmd
    assert "'--mode', 'company-identity'" in cmd
    assert "'--cik-offset'" in cmd
    assert "'--cik-limit'" in cmd


def test_stage0_company_identity_is_strict_not_lenient(definition: dict) -> None:
    """Unlike Branch B's lenient AD-13 pattern (Catch -> proceed anyway), a
    company-identity failure must abort the run: IS_INSIDER derivation
    depends on resolved Company entities, so silently proceeding with
    unresolved company data would defeat this pipeline's purpose."""
    state = definition["States"]["Stage0CompanyIdentity"]
    assert state["Type"] == "Map"
    assert state["MaxConcurrency"] == 1
    assert state["ToleratedFailurePercentage"] == 0
    assert "Catch" not in state


def test_stage0_company_identity_reads_same_cik_windows_manifest(definition: dict) -> None:
    """Reads the same cik_windows.jsonl ComputeWindows writes, so it processes
    identical CIK windows to Branch A/B rather than an independently-resolved list."""
    state = definition["States"]["Stage0CompanyIdentity"]
    key_expr = state["ItemReader"]["Parameters"]["Key.$"]
    branch_a_key_expr = (
        definition["States"]["Stage1Parallel"]["Branches"][0]["States"]
        ["WindowedBootstrap"]["ItemReader"]["Parameters"]["Key.$"]
    )
    assert key_expr == branch_a_key_expr


# -- Issue 1 / 4: Branch B sequencing -----------------------------------------


def test_stage1_parallel_contains_only_branch_a(definition: dict) -> None:
    branches = definition["States"]["Stage1Parallel"]["Branches"]
    assert len(branches) == 1
    combined_cmds = " ".join(
        _command_of_state(state)
        for branch in branches
        for state in branch["States"].values()
    )
    assert "'bootstrap-next'" in combined_cmds
    assert "'bootstrap-fundamentals'" not in combined_cmds


def test_branch_b_modes_run_sequentially_after_stage1_parallel(definition: dict) -> None:
    order = _linear_order(definition)
    for name in (
        "Stage1Parallel",
        "Stage1BEntityFacts",
        "Stage1BPerFiling",
        "Stage1BThirteenF",
        "MdmRun",
    ):
        assert name in order
    assert order.index("Stage1Parallel") < order.index("Stage1BEntityFacts")
    assert order.index("Stage1BEntityFacts") < order.index("Stage1BPerFiling")
    assert order.index("Stage1BPerFiling") < order.index("Stage1BThirteenF")
    assert order.index("Stage1BThirteenF") < order.index("MdmRun")


def test_stage1b_entity_facts_command_shape(definition: dict) -> None:
    cmd = _command_of(definition, "Stage1BEntityFacts")
    assert "'bootstrap-fundamentals'" in cmd
    assert "'--mode', 'entity-facts'" in cmd


def test_stage1b_per_filing_command_shape(definition: dict) -> None:
    cmd = _command_of(definition, "Stage1BPerFiling")
    assert "'bootstrap-fundamentals'" in cmd
    assert "'--mode', 'per-filing'" in cmd


def test_stage1b_thirteenf_command_shape(definition: dict) -> None:
    cmd = _command_of(definition, "Stage1BThirteenF")
    assert "'bootstrap-fundamentals'" in cmd
    assert "'--mode', 'thirteenf'" in cmd


# -- Issue 3: export before graph sync ----------------------------------------


def test_mdm_export_precedes_mdm_sync_graph(definition: dict) -> None:
    order = _linear_order(definition)
    assert "MdmExport" in order
    assert "MdmSync" in order
    assert order.index("MdmExport") < order.index("MdmSync")
    assert "'mdm', 'export'" in _command_of(definition, "MdmExport")
    assert "'mdm', 'sync-graph'" in _command_of(definition, "MdmSync")


def test_mdm_backfill_chains_to_export_not_directly_to_sync(definition: dict) -> None:
    assert definition["States"]["MdmBackfill"]["Next"] == "MdmExport"


# -- fix-pipelines 06-03: DISTRIBUTED Map mode + total_cik_limit CIK-scoping ---------------


def test_windowed_bootstrap_and_stage1b_maps_use_distributed_mode(definition: dict) -> None:
    """Regression guard: AWS Step Functions rejects ItemReader on an INLINE Map
    ("The ItemReader, ItemBatcher and ResultWriter fields are not supported for INLINE
    maps", States.Runtime). This was undetected until 06-03's first-ever dev load_history
    execution failed at WindowedBootstrap with exactly that error — load_history had zero
    prior dev executions (06-02 findings), so the INLINE+ItemReader combination in these
    four Map states was never actually exercised. All four Map states that read
    cik_windows.jsonl via ItemReader must use Mode=DISTRIBUTED (matching the already-working
    pattern in write_ownership_mdm_gold_definition's batch_map elsewhere in this script)."""
    branch_a_states = definition["States"]["Stage1Parallel"]["Branches"][0]["States"]
    windowed_bootstrap = branch_a_states["WindowedBootstrap"]
    assert windowed_bootstrap["ItemProcessor"]["ProcessorConfig"]["Mode"] == "DISTRIBUTED"
    assert windowed_bootstrap["ItemProcessor"]["ProcessorConfig"]["ExecutionType"] == "STANDARD"

    for state_name in ("Stage1BEntityFacts", "Stage1BPerFiling", "Stage1BThirteenF"):
        state = definition["States"][state_name]
        assert state["Type"] == "Map", f"{state_name} should still be a Map state"
        processor_config = state["ItemProcessor"]["ProcessorConfig"]
        assert processor_config["Mode"] == "DISTRIBUTED", (
            f"{state_name} ItemProcessor.ProcessorConfig.Mode must be DISTRIBUTED "
            f"(ItemReader is incompatible with INLINE), got {processor_config.get('Mode')!r}"
        )
        assert processor_config["ExecutionType"] == "STANDARD"


def test_all_item_reader_maps_use_distributed_mode(definition: dict) -> None:
    """Broader structural guard: ANY Map state anywhere in this definition (including
    nested inside Parallel branches) that declares an ItemReader must use
    Mode=DISTRIBUTED — INLINE Maps cannot read from S3 via ItemReader at all."""

    def walk(states: dict, label: str) -> None:
        for name, state in states.items():
            if state.get("Type") == "Map":
                if "ItemReader" in state:
                    mode = state["ItemProcessor"]["ProcessorConfig"].get("Mode")
                    assert mode == "DISTRIBUTED", (
                        f"{label}.{name} has ItemReader but ProcessorConfig.Mode={mode!r} "
                        "(must be DISTRIBUTED)"
                    )
                proc = state["ItemProcessor"]
                walk(proc["States"], f"{label}.{name}(Map)")
            if state.get("Type") == "Parallel":
                for i, branch in enumerate(state["Branches"]):
                    walk(branch["States"], f"{label}.{name}(Parallel[{i}])")

    walk(definition["States"], "top")


def test_compute_windows_command_includes_total_cik_limit(definition: dict) -> None:
    """ComputeWindows always passes an explicit --total-cik-limit (0 = no limit sentinel
    when the caller omits $.total_cik_limit) so operators can bound a load_history run to
    a small company sample (D-02) without mutating shared MDM tracking_status."""
    cmd = _command_of(definition, "ComputeWindows")
    assert "'--total-cik-limit'" in cmd
    assert "$.total_cik_limit" in cmd


def test_total_cik_limit_check_defaults_to_no_limit_sentinel(definition: dict) -> None:
    """TotalCikLimitCheck routes straight to ArtifactPolicyCheck when the caller supplied
    total_cik_limit; otherwise TotalCikLimitDefault injects the sentinel 0 (no limit),
    preserving backward compatibility for every existing --input '{}' caller.
    ArtifactPolicyCheck/Default (added for the opt-in artifact-policy skip flag, see
    CLAUDE.md's artifact-throttle 5-whys mitigation #2) sit between this check and
    ComputeWindows -- both checks' Next targets were updated together, this test now
    reflects that intermediate hop rather than the pre-ArtifactPolicyCheck routing."""
    states = definition["States"]
    check = states["TotalCikLimitCheck"]
    assert check["Type"] == "Choice"
    assert check["Choices"][0]["Variable"] == "$.total_cik_limit"
    assert check["Choices"][0]["IsPresent"] is True
    assert check["Choices"][0]["Next"] == "ArtifactPolicyCheck"
    assert check["Default"] == "TotalCikLimitDefault"

    default_state = states["TotalCikLimitDefault"]
    assert default_state["Type"] == "Pass"
    assert default_state["Result"] == 0
    assert default_state["ResultPath"] == "$.total_cik_limit"
    assert default_state["Next"] == "ArtifactPolicyCheck"


def test_window_size_and_total_cik_limit_checks_precede_compute_windows(definition: dict) -> None:
    order = _linear_order(definition)
    assert order.index("WindowSizeCheck") < order.index("TotalCikLimitCheck") < order.index("ComputeWindows")


# -- ADV fetch pipeline wiring spec (.scratch/adv-fetch-pipeline-wiring, ticket 01):
# AdvBulkFetch stage between Stage1BThirteenF and MdmRun ------------------------


def test_fetch_adv_bulk_stage_runs_after_stage1b_thirteenf_before_mdm_run(definition: dict) -> None:
    order = _linear_order(definition)
    assert "Stage1BThirteenF" in order
    assert "FetchAdvBulk" in order
    assert "IngestAdvBulkSources" in order
    assert "MdmRun" in order
    assert order.index("Stage1BThirteenF") < order.index("FetchAdvBulk")
    assert order.index("FetchAdvBulk") < order.index("IngestAdvBulkSources")
    assert order.index("IngestAdvBulkSources") < order.index("MdmRun")


def test_fetch_adv_bulk_command_shape_with_no_sm_input_overrides(definition: dict) -> None:
    cmd = _command_of(definition, "FetchAdvBulk")
    assert "'fetch-adv-bulk'" in cmd
    assert "'--dataset-period'" in cmd
    assert "'--force'" not in cmd
    assert "'--run-id'" in cmd


def test_dataset_period_check_and_default_precede_force_check(definition: dict) -> None:
    """Mirrors ArtifactPolicyCheck/ArtifactPolicyDefault's existing Check-Default
    pattern: an absent $.dataset_period gets defaulted to an empty string (which
    fetch-adv-bulk's own dispatch already treats the same as omitted) rather than
    the stage failing or a value being required."""
    states = definition["States"]
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


def test_stage1b_thirteenf_routes_into_dataset_period_check(definition: dict) -> None:
    order = _linear_order(definition)
    assert order.index("Stage1BThirteenF") < order.index("DatasetPeriodCheck")
    assert order.index("DatasetPeriodCheck") < order.index("ForceCheck")


def test_force_check_routes_to_two_distinct_fetch_adv_bulk_command_shapes(definition: dict) -> None:
    """--force is a bare boolean CLI flag (action='store_true'), so it cannot be
    conditionally included via States.Format string interpolation the way
    --dataset-period's value can. ForceCheck must instead branch to two literal
    Task definitions -- one whose command includes the --force token, one that
    omits it -- both converging on the same next state."""
    states = definition["States"]
    force_check = states["ForceCheck"]
    assert force_check["Type"] == "Choice"
    assert _choice_next(force_check, {}) == "FetchAdvBulk"
    assert _choice_next(force_check, {"force": False}) == "FetchAdvBulk"
    assert _choice_next(force_check, {"force": True}) == "FetchAdvBulkForced"
    assert _choice_next(force_check, {"force": "true"}) == "InvalidForceInput"

    no_force_cmd = _command_of(definition, "FetchAdvBulk")
    forced_cmd = _command_of(definition, "FetchAdvBulkForced")
    assert "'--force'" not in no_force_cmd
    assert "'--force'" in forced_cmd
    # Otherwise identical apart from the --force token.
    assert no_force_cmd.replace(", '--force'", "") == forced_cmd.replace(", '--force'", "")

    assert states["FetchAdvBulk"]["Next"] == "IngestAdvBulkSources"
    assert states["FetchAdvBulkForced"]["Next"] == "IngestAdvBulkSources"


def test_ingest_adv_bulk_sources_references_fetch_adv_bulk_manifest_path(definition: dict) -> None:
    """ingest-relationship-sources' --source-manifest must resolve to the same
    deterministic, run-id-scoped path fetch-adv-bulk itself writes to
    (bronze_root/runs/fetch-adv-bulk/<run-id>/source_manifest.json, confirmed
    against tests/application/test_fetch_adv_bulk_command.py) -- the state
    machine re-derives this independently rather than capturing FetchAdvBulk's
    literal output, mirroring how Stage0CompanyIdentity re-derives
    cik_windows.jsonl's S3 key instead of passing it through execution state."""
    cmd = _command_of(definition, "IngestAdvBulkSources")
    assert "'ingest-relationship-sources'" in cmd
    assert "'--source-manifest'" in cmd
    assert "runs/fetch-adv-bulk/" in cmd
    assert "source_manifest.json" in cmd
    assert "$$.Execution.Name" in cmd


def test_fetch_adv_bulk_and_ingest_adv_bulk_sources_catch_falls_through_to_mdm_run(
    definition: dict,
) -> None:
    """A transient ADV fetch/ingest failure must never abort the rest of
    load_history -- matches the existing Branch B / AD-13 lenient pattern, and
    directly implements the ADV Pipeline map's standing requirement (ticket 02's
    Notes) that entity resolution/graph sync must never gate on ADV data."""
    for state_name in ("FetchAdvBulk", "FetchAdvBulkForced", "IngestAdvBulkSources"):
        state = definition["States"][state_name]
        assert state.get("Catch") == [
            {"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "MdmRun"}
        ], f"{state_name} missing lenient Catch-to-MdmRun"


def test_stage1b_thirteenf_catch_routes_into_adv_bulk_fetch_not_around_it(
    definition: dict,
) -> None:
    """Regression guard: Stage1BThirteenF's own (pre-existing) lenient Catch must
    route into DatasetPeriodCheck, not straight to MdmRun -- otherwise a Branch B
    thirteenf failure (an expected, accepted AD-13 outcome, not a rare case)
    would silently skip the entire AdvBulkFetch stage instead of still attempting
    it before MDM runs."""
    catch = definition["States"]["Stage1BThirteenF"]["Catch"]
    assert catch == [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "DatasetPeriodCheck"}]


def test_fetch_and_ingest_adv_bulk_states_preserve_sm_input_via_result_path_null(
    definition: dict,
) -> None:
    """Regression guard for the D-15 bug class documented on the `seed` state
    above: an ecs:runTask.sync Task without ResultPath=null replaces $ entirely
    with its own result, destroying $.dataset_period/$.force for any state
    downstream of this stage that might need them."""
    for state_name in ("FetchAdvBulk", "FetchAdvBulkForced", "IngestAdvBulkSources"):
        assert definition["States"][state_name]["ResultPath"] is None, (
            f"{state_name} must set ResultPath=null to preserve $ into the next state"
        )


def test_firm_roster_stage_runs_after_ingest_adv_bulk_sources_before_mdm_run(definition: dict) -> None:
    order = _linear_order(definition)
    assert "IngestAdvBulkSources" in order
    assert "FetchFirmRoster" in order
    assert "IngestFirmRosterSources" in order
    assert "MdmRun" in order
    assert order.index("IngestAdvBulkSources") < order.index("FetchFirmRoster")
    assert order.index("FetchFirmRoster") < order.index("IngestFirmRosterSources")
    assert order.index("IngestFirmRosterSources") < order.index("MdmRun")


def test_ingest_adv_bulk_sources_routes_into_firm_roster_force_check_not_around_it(
    definition: dict,
) -> None:
    """Regression guard mirroring test_stage1b_thirteenf_catch_routes_into_adv_
    bulk_fetch_not_around_it above: IngestAdvBulkSources' success-path Next must
    route into FirmRosterForceCheck, not straight to MdmRun -- otherwise the
    Firm Roster cross-check stage would be silently skipped every run."""
    assert definition["States"]["IngestAdvBulkSources"]["Next"] == "FirmRosterForceCheck"


def test_firm_roster_force_check_routes_to_two_distinct_fetch_firm_roster_command_shapes(
    definition: dict,
) -> None:
    """Mirrors test_force_check_routes_to_two_distinct_fetch_adv_bulk_command_
    shapes above: FirmRosterForceCheck re-inspects the same $.force SM-input
    field (rather than ForceCheck routing here directly, since a Choice state
    can only have one Next per branch and ForceCheck already routes to
    FetchAdvBulk/FetchAdvBulkForced)."""
    states = definition["States"]
    force_check = states["FirmRosterForceCheck"]
    assert force_check["Type"] == "Choice"
    assert _choice_next(force_check, {}) == "FetchFirmRoster"
    assert _choice_next(force_check, {"force": False}) == "FetchFirmRoster"
    assert _choice_next(force_check, {"force": True}) == "FetchFirmRosterForced"
    assert _choice_next(force_check, {"force": "true"}) == "InvalidForceInput"

    no_force_cmd = _command_of(definition, "FetchFirmRoster")
    forced_cmd = _command_of(definition, "FetchFirmRosterForced")
    assert "'fetch-firm-roster'" in no_force_cmd
    assert "'--force'" not in no_force_cmd
    assert "'--force'" in forced_cmd
    assert no_force_cmd.replace(", '--force'", "") == forced_cmd.replace(", '--force'", "")

    assert states["FetchFirmRoster"]["Next"] == "IngestFirmRosterSources"
    assert states["FetchFirmRosterForced"]["Next"] == "IngestFirmRosterSources"


def test_ingest_firm_roster_sources_references_fetch_firm_roster_manifest_path(definition: dict) -> None:
    """Mirrors test_ingest_adv_bulk_sources_references_fetch_adv_bulk_manifest_
    path above: --source-manifest must resolve to the same deterministic,
    run-id-scoped path fetch-firm-roster itself writes to."""
    cmd = _command_of(definition, "IngestFirmRosterSources")
    assert "'ingest-relationship-sources'" in cmd
    assert "'--source-manifest'" in cmd
    assert "runs/fetch-firm-roster/" in cmd
    assert "source_manifest.json" in cmd
    assert "$$.Execution.Name" in cmd


def test_fetch_and_ingest_firm_roster_catch_falls_through_to_mdm_run(definition: dict) -> None:
    """Mirrors test_fetch_adv_bulk_and_ingest_adv_bulk_sources_catch_falls_
    through_to_mdm_run above: a transient Firm Roster fetch/ingest failure
    must never abort the rest of load_history -- this cross-check is purely
    additive visibility, per the parent spec."""
    for state_name in ("FetchFirmRoster", "FetchFirmRosterForced", "IngestFirmRosterSources"):
        state = definition["States"][state_name]
        assert state.get("Catch") == [
            {"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "MdmRun"}
        ], f"{state_name} missing lenient Catch-to-MdmRun"


def test_fetch_and_ingest_firm_roster_states_preserve_sm_input_via_result_path_null(
    definition: dict,
) -> None:
    """Mirrors test_fetch_and_ingest_adv_bulk_states_preserve_sm_input_via_
    result_path_null above -- same D-15 bug class."""
    for state_name in ("FetchFirmRoster", "FetchFirmRosterForced", "IngestFirmRosterSources"):
        assert definition["States"][state_name]["ResultPath"] is None, (
            f"{state_name} must set ResultPath=null to preserve $ into the next state"
        )
