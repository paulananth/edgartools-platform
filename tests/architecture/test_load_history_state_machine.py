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
        # sec_fetch_active lease (release-readiness ticket 84): Default is the
        # fail-closed deferred path, not the happy path -- trace the explicit
        # lease_acquired=True branch instead, matching this repo's convention
        # for LeaseAcquiredCheck in test_daily_incremental_state_machine.py.
        "SecFetchLeaseAcquiredCheck": "SeedUniverse",
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
    """Next is AcquireSecFetchLease, not SeedUniverse directly (release-
    readiness ticket 84) -- the cross-command sec_fetch_active lease gates
    entry into the whole real-SEC-fetching span."""
    states = definition["States"]
    assert definition["StartAt"] == "ValidateForceInput"
    validation = states["ValidateForceInput"]
    assert _choice_next(validation, {}) == "ForceDefault"
    assert _choice_next(validation, {"force": False}) == "AcquireSecFetchLease"
    assert _choice_next(validation, {"force": True}) == "AcquireSecFetchLease"
    assert _choice_next(validation, {"force": 1}) == "InvalidForceInput"

    assert states["ForceDefault"] == {
        "Type": "Pass",
        "Comment": "Normalize an omitted operator force input to false.",
        "Result": False,
        "ResultPath": "$.force",
        "Next": "AcquireSecFetchLease",
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

    branch_a_states = definition["States"]["IngestBronzeAndSilver"]["Branches"][0]["States"]
    per_window_cmd = _command_of_state(branch_a_states["WindowedBootstrap"])
    assert f"'--tracking-status-filter', '{LOAD_HISTORY_TRACKING_STATUS_FILTER}'" in per_window_cmd


def test_windowed_bootstrap_is_silver_only(definition: dict) -> None:
    branch_a_states = definition["States"]["IngestBronzeAndSilver"]["Branches"][0]["States"]
    per_window_cmd = _command_of_state(branch_a_states["WindowedBootstrap"])
    assert "'bootstrap-next'" in per_window_cmd
    assert "'--silver-only'" in per_window_cmd


def test_windowed_bootstrap_projects_artifact_policy_into_each_item(
    definition: dict,
) -> None:
    """The S3 JSONL rows contain only window bounds, while RunWindow also reads
    the execution-scoped artifact policy. The Distributed Map must combine both
    inputs before starting each child execution."""
    branch_a_states = definition["States"]["IngestBronzeAndSilver"]["Branches"][0]["States"]
    windowed_bootstrap = branch_a_states["WindowedBootstrap"]

    assert windowed_bootstrap["ItemSelector"] == {
        "window_offset.$": "$$.Map.Item.Value.window_offset",
        "window_limit.$": "$$.Map.Item.Value.window_limit",
        "artifact_policy.$": "$.artifact_policy",
        "filing_lookback_years.$": "$.filing_lookback_years",
    }


@pytest.mark.parametrize("artifact_policy", ["skip", "all_attachments"])
def test_execution_routing_survives_compute_windows_to_windowed_bootstrap(
    definition: dict, artifact_policy: str,
) -> None:
    """Successful ECS/Map outputs must not replace the normalized execution
    input before WindowedBootstrap resolves its execution-scoped selector."""
    states = definition["States"]
    state_input = {
        "force": False,
        "window_size": 1,
        "total_cik_limit": 2,
        "artifact_policy": artifact_policy,
        "filing_lookback_years": 2,
    }
    synthetic_state_output = {"ecs_task_result": "successful"}

    # This is the successful top-level route from normalized operator input to
    # the branch that reads $.artifact_policy. Under ASL, an omitted ResultPath
    # defaults to "$" and replaces the entire state input; ResultPath null
    # discards the state result and preserves its input.
    for state_name in (
        "SeedUniverse",
        "MdmSeedUniverse",
        "ComputeWindows",
        "IngestBronzeAndSilver",
    ):
        state = states[state_name]
        result_path = state.get("ResultPath", "$")
        if result_path == "$":
            state_input = synthetic_state_output
        elif result_path is not None:
            raise AssertionError(
                f"test route does not model non-root ResultPath {result_path!r} "
                f"on {state_name}"
            )

    selector = states["IngestBronzeAndSilver"]["Branches"][0]["States"]
    selector = selector["WindowedBootstrap"]["ItemSelector"]
    execution_scoped_paths = {
        target: path.removeprefix("$.")
        for target, path in selector.items()
        if path.startswith("$.")
    }
    assert execution_scoped_paths == {
        "artifact_policy.$": "artifact_policy",
        "filing_lookback_years.$": "filing_lookback_years",
    }
    assert state_input[execution_scoped_paths["artifact_policy.$"]] == artifact_policy
    assert state_input[execution_scoped_paths["filing_lookback_years.$"]] == 2


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


# -- Issue 1 / 4: Branch B sequencing -----------------------------------------


def test_stage1_parallel_contains_only_branch_a(definition: dict) -> None:
    branches = definition["States"]["IngestBronzeAndSilver"]["Branches"]
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
        "IngestBronzeAndSilver",
        "FetchEntityFacts",
        "FetchPerFilingFundamentals",
        "FetchThirteenFHoldings",
        "MdmRun",
    ):
        assert name in order
    assert order.index("IngestBronzeAndSilver") < order.index("FetchEntityFacts")
    assert order.index("FetchEntityFacts") < order.index("FetchPerFilingFundamentals")
    assert order.index("FetchPerFilingFundamentals") < order.index("FetchThirteenFHoldings")
    assert order.index("FetchThirteenFHoldings") < order.index("MdmRun")


def test_stage1b_entity_facts_command_shape(definition: dict) -> None:
    cmd = _command_of(definition, "FetchEntityFacts")
    assert "'bootstrap-fundamentals'" in cmd
    assert "'--mode', 'entity-facts'" in cmd


def test_stage1b_per_filing_command_shape(definition: dict) -> None:
    cmd = _command_of(definition, "FetchPerFilingFundamentals")
    assert "'bootstrap-fundamentals'" in cmd
    assert "'--mode', 'per-filing'" in cmd


def test_stage1b_thirteenf_command_shape(definition: dict) -> None:
    cmd = _command_of(definition, "FetchThirteenFHoldings")
    assert "'bootstrap-fundamentals'" in cmd
    assert "'--mode', 'thirteenf'" in cmd


def test_stage1b_maps_use_large_task_definition(definition: dict) -> None:
    """2026-08-14, ecs-cost-sizing ticket 20: FetchEntityFacts OOM'd (exit
    137) on all 3 configured attempts on wh_medium_arn during task #35's
    live full-universe load_history run, root-caused to the shared
    silver-publish merge step materializing a cold-start table's entire
    delta into Python. FetchPerFilingFundamentals then also OOM'd twice on the same
    run before this fix landed. Moved all three Stage1B modes to
    wh_large_arn as a stopgap alongside the structural fix in
    silver_protection.py, matching the ComputeWindows/SeedUniverse/
    WindowedBootstrap precedent above -- FetchThirteenFHoldings is included
    preemptively (not yet independently observed OOMing) since it shares
    the identical merge_candidate_into_canonical publish-step risk and
    sec_thirteenf_holding's per-filing fan-out is at least as large."""
    for state_name, inner_state_name in (
        ("FetchEntityFacts", "RunFundamentalsEntityFacts"),
        ("FetchPerFilingFundamentals", "RunFundamentalsPerFiling"),
        ("FetchThirteenFHoldings", "RunFundamentalsThirteenF"),
    ):
        inner_state = definition["States"][state_name]["ItemProcessor"]["States"][inner_state_name]
        assert inner_state["Parameters"]["TaskDefinition"] == "arn:wh-large", (
            f"{state_name}.{inner_state_name} should run on wh_large_arn"
        )


def test_stage1b_maps_tolerate_isolated_window_failures(definition: dict) -> None:
    """2026-08-14, ecs-cost-sizing ticket 21: at ToleratedFailurePercentage=0, window 1
    of N exhausting its retries aborted these Maps immediately, abandoning every other
    PENDING window without even attempting it. Live evidence from load_history retry7:
    describe-map-run on all three Maps showed succeeded=0, failed=1, pending=51 (of 53
    total windows) -- a 16-hour execution that reported SUCCEEDED overall while adding
    zero net-new entity-facts/per-filing/13F coverage. Raised to 15% so an isolated bad
    window (a huge filer, a transient SEC 5xx) doesn't zero out the rest of the universe,
    while a systemic break still hard-stops well before every window is attempted."""
    for state_name in ("FetchEntityFacts", "FetchPerFilingFundamentals", "FetchThirteenFHoldings"):
        assert definition["States"][state_name]["ToleratedFailurePercentage"] == 15, (
            f"{state_name} should tolerate isolated window failures, not abort on the first one"
        )


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
    branch_a_states = definition["States"]["IngestBronzeAndSilver"]["Branches"][0]["States"]
    windowed_bootstrap = branch_a_states["WindowedBootstrap"]
    assert windowed_bootstrap["ItemProcessor"]["ProcessorConfig"]["Mode"] == "DISTRIBUTED"
    assert windowed_bootstrap["ItemProcessor"]["ProcessorConfig"]["ExecutionType"] == "STANDARD"

    for state_name in ("FetchEntityFacts", "FetchPerFilingFundamentals", "FetchThirteenFHoldings"):
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


def test_compute_windows_uses_large_task_definition(definition: dict) -> None:
    """Company Identity Hydrate Elimination map, ticket 03: ComputeWindows now
    also calls persist_run_manifest, which reads the full canonical
    silver.duckdb into a Python bytes object for its immutable reference
    snapshot -- an added working-set cost on top of the pre-existing full
    hydrate, on the same canonical file whose growth already caused
    Stage0CompanyIdentity's live OOM. Belt-and-suspenders headroom."""
    assert definition["States"]["ComputeWindows"]["Parameters"]["TaskDefinition"] == "arn:wh-large"


def test_seed_universe_uses_large_task_definition(definition: dict) -> None:
    """2026-08-09: task #35's first full-universe load_history execution
    OOM'd (exit 137) on SeedUniverse running wh_medium_arn -- seed-universe's
    run_command() dispatch unconditionally hydrates the full canonical
    silver.duckdb (1.5GB+ and growing, the same file whose growth already
    caused ComputeWindows/Stage0CompanyIdentity's OOMs above) before its own
    db.get_active_ciks()/tracking-status logic runs. Moved to wh_large_arn to
    match that established precedent."""
    assert definition["States"]["SeedUniverse"]["Parameters"]["TaskDefinition"] == "arn:wh-large"


def test_windowed_bootstrap_uses_large_task_definition(definition: dict) -> None:
    """2026-08-10: task #35's full-universe load_history execution OOM'd
    (exit 137) twice on WindowedBootstrap's RunWindow (bootstrap-next
    --silver-only, a 500-CIK window) running wh_medium_arn, exhausting the
    Map's retry budget and failing the whole execution. CloudWatch showed a
    steady ~600MB -> ~2.4GB climb over the task's ~80-minute lifetime
    (accumulation in _capture_submission_bronze_snapshots, not a one-time
    buffer spike) -- moved to wh_large_arn as a stopgap matching the
    ComputeWindows/Stage0CompanyIdentity/gold-refresh/seed-universe
    precedent above, while the underlying accumulation is tracked
    separately."""
    branch_a_states = definition["States"]["IngestBronzeAndSilver"]["Branches"][0]["States"]
    run_window = branch_a_states["WindowedBootstrap"]["ItemProcessor"]["States"]["RunWindow"]
    assert run_window["Parameters"]["TaskDefinition"] == "arn:wh-large"


def test_window_size_default_is_1000(definition: dict) -> None:
    """2026-08-14, ecs-cost-sizing credit-consumption finding: every window
    completion triggers a separate EDGARTOOLS_GOLD.REFRESH_AFTER_LOAD call in
    Snowflake (confirmed live via QUERY_ATTRIBUTION_HISTORY: 5,988 calls/32.2
    credits over 7 days on EDGARTOOLS_PROD_REFRESH_WH, spiking on days
    load_history ran many small windows). Doubling window_size 500 -> 1000
    roughly halves REFRESH_AFTER_LOAD call volume per full-universe run.
    Capped at 2x, not larger, because window_size also scales
    WindowedBootstrap's still-unfixed _capture_submission_bronze_snapshots
    accumulation (test_windowed_bootstrap_uses_large_task_definition above)
    -- 1000 stays inside the same wh_large_arn/wh_medium_arn headroom ratio
    that precedent already proved safe, rather than gambling on unmeasured
    slack beyond it."""
    assert definition["States"]["WindowSizeDefault"]["Result"] == 1000


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


# -- filing_lookback_years: general filing-discovery date bound ---------------


def test_artifact_policy_check_routes_into_filing_lookback_years_check(definition: dict) -> None:
    states = definition["States"]
    assert states["ArtifactPolicyCheck"]["Choices"][0]["Next"] == "FilingLookbackYearsCheck"
    assert states["ArtifactPolicyDefault"]["Next"] == "FilingLookbackYearsCheck"


def test_filing_lookback_years_check_defaults_to_two_years(definition: dict) -> None:
    """FilingLookbackYearsCheck routes straight to ComputeWindows when the caller
    supplied filing_lookback_years; otherwise FilingLookbackYearsDefault injects 2
    (load_history-specific default, deliberately different from the CLI/code-level
    default of 0/disabled used by every other bootstrap-next caller)."""
    states = definition["States"]
    check = states["FilingLookbackYearsCheck"]
    assert check["Type"] == "Choice"
    assert check["Choices"][0]["Variable"] == "$.filing_lookback_years"
    assert check["Choices"][0]["IsPresent"] is True
    assert check["Choices"][0]["Next"] == "ComputeWindows"
    assert check["Default"] == "FilingLookbackYearsDefault"

    default_state = states["FilingLookbackYearsDefault"]
    assert default_state["Type"] == "Pass"
    assert default_state["Result"] == 2
    assert default_state["ResultPath"] == "$.filing_lookback_years"
    assert default_state["Next"] == "ComputeWindows"


def test_windowed_bootstrap_command_includes_filing_lookback_years(definition: dict) -> None:
    branch_a_states = definition["States"]["IngestBronzeAndSilver"]["Branches"][0]["States"]
    per_window_cmd = _command_of_state(branch_a_states["WindowedBootstrap"])
    assert "'--filing-lookback-years'" in per_window_cmd
    assert "$.filing_lookback_years" in per_window_cmd


def test_window_size_total_cik_limit_artifact_policy_filing_lookback_checks_precede_compute_windows(
    definition: dict,
) -> None:
    order = _linear_order(definition)
    assert (
        order.index("WindowSizeCheck")
        < order.index("TotalCikLimitCheck")
        < order.index("ArtifactPolicyCheck")
        < order.index("FilingLookbackYearsCheck")
        < order.index("ComputeWindows")
    )


# -- ADV fetch pipeline wiring spec (.scratch/adv-fetch-pipeline-wiring, ticket 01):
# AdvBulkFetch stage between FetchThirteenFHoldings and MdmRun ------------------------


def test_fetch_adv_bulk_stage_runs_after_stage1b_thirteenf_before_mdm_run(definition: dict) -> None:
    order = _linear_order(definition)
    assert "FetchThirteenFHoldings" in order
    assert "FetchAdvBulk" in order
    assert "IngestAdvBulkSources" in order
    assert "MdmRun" in order
    assert order.index("FetchThirteenFHoldings") < order.index("FetchAdvBulk")
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
    assert order.index("FetchThirteenFHoldings") < order.index("DatasetPeriodCheck")
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
    Notes) that entity resolution/graph sync must never gate on ADV data.
    Catch falls through to ReleaseSecFetchLease, not MdmRun directly (release-
    readiness ticket 84) -- these fetch stages are still inside the
    sec_fetch_active fetch-heavy span, so a failure must still release the
    lease before proceeding to MDM."""
    for state_name in ("FetchAdvBulk", "FetchAdvBulkForced", "IngestAdvBulkSources"):
        state = definition["States"][state_name]
        assert state.get("Catch") == [
            {"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "ReleaseSecFetchLease"}
        ], f"{state_name} missing lenient Catch-to-ReleaseSecFetchLease"
    assert definition["States"]["ReleaseSecFetchLease"]["Next"] == "MdmRun"


def test_stage1b_thirteenf_catch_routes_into_adv_bulk_fetch_not_around_it(
    definition: dict,
) -> None:
    """Regression guard: FetchThirteenFHoldings's own (pre-existing) lenient Catch must
    route into DatasetPeriodCheck, not straight to MdmRun -- otherwise a Branch B
    thirteenf failure (an expected, accepted AD-13 outcome, not a rare case)
    would silently skip the entire AdvBulkFetch stage instead of still attempting
    it before MDM runs."""
    catch = definition["States"]["FetchThirteenFHoldings"]["Catch"]
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
    additive visibility, per the parent spec. Catch falls through to
    ReleaseSecFetchLease, not MdmRun directly (release-readiness ticket 84)."""
    for state_name in ("FetchFirmRoster", "FetchFirmRosterForced", "IngestFirmRosterSources"):
        state = definition["States"][state_name]
        assert state.get("Catch") == [
            {"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "ReleaseSecFetchLease"}
        ], f"{state_name} missing lenient Catch-to-ReleaseSecFetchLease"
    assert definition["States"]["ReleaseSecFetchLease"]["Next"] == "MdmRun"


def test_fetch_and_ingest_firm_roster_states_preserve_sm_input_via_result_path_null(
    definition: dict,
) -> None:
    """Mirrors test_fetch_and_ingest_adv_bulk_states_preserve_sm_input_via_
    result_path_null above -- same D-15 bug class."""
    for state_name in ("FetchFirmRoster", "FetchFirmRosterForced", "IngestFirmRosterSources"):
        assert definition["States"][state_name]["ResultPath"] is None, (
            f"{state_name} must set ResultPath=null to preserve $ into the next state"
        )


# ---------------------------------------------------------------------------
# sec_fetch_active cross-command lease (release-readiness ticket 84):
# AcquireSecFetchLease -> ReadSecFetchLeaseResult -> SecFetchLeaseAcquiredCheck
# -> {SeedUniverse | SecFetchDeferred}, and ReleaseSecFetchLease before MdmRun.
# load_history was restructured from the original parallel bootstrap-batch xN
# Map into a sequential (MaxConcurrency=1) windowed pipeline (see the "Phased
# pipeline" comment in the deploy script) -- no fan-out concern remains, so a
# single acquire/release wraps the whole real-SEC-fetching span.
# ---------------------------------------------------------------------------


def test_load_history_acquires_sec_fetch_lease_before_seed_universe(definition: dict) -> None:
    states = definition["States"]
    assert states["ForceDefault"]["Next"] == "AcquireSecFetchLease"

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
    assert check["Choices"][0]["Next"] == "SeedUniverse"
    assert check["Default"] == "SecFetchDeferred"

    deferred = states["SecFetchDeferred"]
    assert deferred["Type"] == "Pass"
    assert deferred["End"] is True
    assert deferred["Parameters"]["disposition"] == "sec_fetch_deferred"


def test_load_history_no_operator_notification_on_sec_fetch_defer(definition: dict) -> None:
    """load_history is operator-triggered ad-hoc (like bootstrap/bootstrap_full/
    targeted_resync), unlike the scheduled daily_incremental -- no SNS
    notification on defer, the operator is already watching the run."""
    assert "NotifySecFetchDeferred" not in definition["States"]


def test_load_history_releases_sec_fetch_lease_before_mdm_run(definition: dict) -> None:
    states = definition["States"]
    assert states["IngestFirmRosterSources"]["Next"] == "ReleaseSecFetchLease"

    release = states["ReleaseSecFetchLease"]
    cmd = release["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "release-sec-fetch-lease" in cmd
    assert release["ResultPath"] is None
    assert release["Next"] == "MdmRun"
    assert release["Catch"] == [
        {"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "ReleaseSecFetchLeaseFailedNonFatal"}
    ]

    fallback = states["ReleaseSecFetchLeaseFailedNonFatal"]
    assert fallback["Type"] == "Pass"
    assert fallback["Next"] == "MdmRun"
    assert "End" not in fallback


def test_sec_fetch_lease_read_result_key_matches_the_real_path_resolver(definition: dict) -> None:
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
    key_expr = definition["States"]["ReadSecFetchLeaseResult"]["Parameters"]["Key.$"]
    assert key_expr == expected_key_expr


def test_load_history_sec_fetch_lease_spans_the_whole_windowed_pipeline(definition: dict) -> None:
    """The lease must be held across SeedUniverse, MdmSeedUniverse,
    IngestBronzeAndSilver/Stage1B, and the ADV/firm-roster chain -- i.e. acquired
    strictly before all of them and released strictly after all of them,
    with no path that reaches MdmRun without passing through
    ReleaseSecFetchLease first. (Stage0CompanyIdentity/ReduceIdentityRefresh
    removed -- stage0-stage1-consolidation wayfinder map, ticket 02/04 --
    IngestBronzeAndSilver's WindowedBootstrap now covers the identity capture they
    used to do as a byproduct of its own submissions capture.)"""
    order = _linear_order(definition)
    assert order.index("AcquireSecFetchLease") < order.index("SeedUniverse")
    assert order.index("SeedUniverse") < order.index("MdmSeedUniverse")
    assert order.index("MdmSeedUniverse") < order.index("IngestBronzeAndSilver")
    assert "ReleaseSecFetchLease" in order
    assert order.index("IngestBronzeAndSilver") < order.index("ReleaseSecFetchLease")
    assert order.index("ReleaseSecFetchLease") < order.index("MdmRun")


def test_load_history_previously_uncaught_states_release_lease_on_failure(definition: dict) -> None:
    """release-readiness ticket 86: SeedUniverse/MdmSeedUniverse/
    ComputeWindows/IngestBronzeAndSilver had no Catch at all -- a real failure in
    any of them wedged sec_fetch_active for the full 16h stale-reclaim
    window. Deliberately excludes FetchEntityFacts/FetchPerFilingFundamentals/
    FetchThirteenFHoldings, which AD-13 already routes forward on failure (still
    reaching ReleaseSecFetchLease on the happy path), and
    FetchAdvBulk/IngestFirmRosterSources etc., which already had their own
    Catch (adv_bulk_fetch_catch, unchanged by this ticket). (Stage0Company
    Identity/ReduceIdentityRefresh no longer exist in this state machine --
    stage0-stage1-consolidation wayfinder map, ticket 02/04.)"""
    states = definition["States"]
    expected_catch = [
        {"ErrorEquals": ["States.ALL"], "ResultPath": "$.sec_fetch_task_error", "Next": "ReleaseSecFetchLeaseAfterFailure"}
    ]
    for previously_uncaught_state in (
        "SeedUniverse",
        "MdmSeedUniverse",
        "ComputeWindows",
        "IngestBronzeAndSilver",
    ):
        assert states[previously_uncaught_state]["Catch"] == expected_catch

    for ad13_state in ("FetchEntityFacts", "FetchPerFilingFundamentals", "FetchThirteenFHoldings"):
        catch = states[ad13_state]["Catch"]
        assert catch != expected_catch
        assert catch[0]["Next"] != "ReleaseSecFetchLeaseAfterFailure"

    release_after_failure = states["ReleaseSecFetchLeaseAfterFailure"]
    cmd = release_after_failure["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "release-sec-fetch-lease" in cmd
    assert release_after_failure["ResultPath"] is None
    assert release_after_failure["Next"] == "SecFetchTaskFailed"
    assert release_after_failure["Catch"] == [
        {"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "SecFetchTaskFailed"}
    ]

    failed = states["SecFetchTaskFailed"]
    assert failed["Type"] == "Fail"
    assert failed["ErrorPath"] == "$.sec_fetch_task_error.Error"
    assert failed["CausePath"] == "$.sec_fetch_task_error.Cause"
