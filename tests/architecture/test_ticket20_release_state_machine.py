from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "deploy-aws-application.sh"


def _definition(tmp_path: Path) -> dict:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index("write_bronze_seed_silver_gold_definition() {\n")
    end = text.index("\nPY\n}\n", start) + len("\nPY\n}\n")
    function_path = tmp_path / "function.sh"
    function_path.write_text(text[start:end], encoding="utf-8")
    output_path = tmp_path / "definition.json"
    driver = tmp_path / "driver.sh"
    driver.write_text(
        "set -euo pipefail\n"
        'CLUSTER_ARN="arn:cluster"\n'
        'BRONZE_BUCKET_NAME="bronze-bucket"\n'
        'WAREHOUSE_BUCKET_NAME="warehouse-bucket"\n'
        "PUBLIC_SUBNET_IDS_JSON='[\"subnet-1\"]'\n"
        "SECURITY_GROUP_IDS_JSON='[\"sg-1\"]'\n"
        "BOOTSTRAP_BATCH_CONCURRENCY=4\n"
        "MDM_RUN_LIMIT=100\n"
        "MDM_GRAPH_LIMIT=100\n"
        f'SCRIPT_DIR="{(REPO_ROOT / "infra" / "scripts").as_posix()}"\n'
        f'source "{function_path}"\n'
        f'write_bronze_seed_silver_gold_definition "{output_path}" '
        '"arn:warehouse-medium" "arn:mdm-small" "arn:mdm-medium" "arn:warehouse-large"\n',
        encoding="utf-8",
    )
    result = subprocess.run(["bash", str(driver)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(output_path.read_text(encoding="utf-8"))


def test_strict_ticket20_path_generates_valid_fail_closed_definition(tmp_path: Path) -> None:
    definition = _definition(tmp_path)
    states = definition["States"]

    assert definition["StartAt"] == "ReleaseModeCheck"
    # pipeline-resumability ticket 02: the default (non-strict) path now
    # routes through resume_from_run_id normalization before BatchSizeCheck.
    assert states["ReleaseModeCheck"]["Default"] == "ResumeFromRunIdPresenceCheck"
    assert states["ResumeFromRunIdPresenceCheck"]["Default"] == "ResumeFromRunIdDefault"
    assert states["ResumeFromRunIdDefault"]["Next"] == "ResumeFromRunIdCheck"
    assert states["ResumeFromRunIdCheck"]["Default"] == "BatchSizeCheck"
    assert (
        states["ResumeFromRunIdCheck"]["Choices"][0]["Next"] == "ComputeRemainingBatches"
    )
    assert states["ComputeRemainingBatches"]["Next"] == "BatchSilver"
    assert "Retry" not in states["ComputeRemainingBatches"]
    clauses = states["StrictManifestCheck"]["Choices"][0]["And"]
    required_inputs = {
        "$.attestations.warehouse",
        "$.attestations.mdm",
        "$.attestations.graph",
        "$.attestations.release_data_operator",
        "$.attestations.release_owner",
    }
    for variable in {
        "$.candidate_manifest_key",
        "$.candidate_batches_key",
        *required_inputs,
    }:
        assert {"Variable": variable, "IsPresent": True} in clauses
        assert {"Variable": variable, "IsString": True} in clauses
        assert {"Not": {"Variable": variable, "StringEquals": ""}} in clauses
    assert not any(clause.get("StringMatches") == "?*" for clause in clauses)
    strict_map = states["StrictBatchSilver"]
    # Lowered 4->2 2026-07-22: every concurrently-finishing batch publishes to
    # the same canonical silver.duckdb via an ETag-guarded promote, so N-way
    # concurrency is an N-way race on that one object -- production hit this
    # repeatedly at MaxConcurrency=4 (PromotionConflictError aborting an
    # otherwise-complete batch).
    assert strict_map["MaxConcurrency"] == 2
    assert strict_map["ToleratedFailurePercentage"] == 0
    # Ticket 21: MDM before reconcile so IS_INSIDER exists for insider coverage.
    assert strict_map["Next"] == "StrictMdmRun"
    assert strict_map["ItemSelector"]["release_run_id.$"] == "$$.Execution.Name"
    command = strict_map["ItemProcessor"]["States"]["RunStrictBatch"]["Parameters"][
        "Overrides"
    ]["ContainerOverrides"][0]["Command.$"]
    assert "'--release-mode'" in command
    assert "'--candidate-manifest'" in command
    assert "branch_b_deferred" in command
    assert "$.release_run_id" in command
    assert "$$.Execution.Name" not in command
    assert "Retry" not in strict_map["ItemProcessor"]["States"]["RunStrictBatch"]
    # PR #139: strict Ticket 20 fails closed on graph parity -- none of the
    # graph-publishing chain (sync/verify-candidate/activate/final-verify)
    # may have a Catch, or a bad candidate/activation could silently fall
    # through to StrictGoldRefresh instead of failing the execution.
    assert "Catch" not in states["StrictMdmSync"]
    assert "Catch" not in states["StrictMdmSyncIdempotency"]
    assert "Catch" not in states["StrictMdmVerifyCandidate"]
    assert "Catch" not in states["StrictMdmActivate"]
    assert "Catch" not in states["StrictMdmVerify"]
    assert "Catch" not in states["StrictInsiderCoverage"]
    assert states["StrictMdmRun"]["Next"] == "StrictMdmBackfill"
    assert states["StrictMdmBackfill"]["Next"] == "StrictMdmIdempotency"
    assert states["StrictMdmIdempotency"]["Next"] == "StrictInsiderCoverage"
    assert states["StrictInsiderCoverage"]["Next"] == "ReconcileRelationshipRelease"
    assert states["ReconcileRelationshipRelease"]["Next"] == "StrictMdmExport"
    assert states["StrictMdmExport"]["Next"] == "StrictMdmSync"
    assert states["StrictMdmSync"]["Next"] == "StrictMdmSyncIdempotency"
    assert states["StrictMdmSyncIdempotency"]["Next"] == "StrictMdmVerifyCandidate"
    assert states["StrictMdmVerifyCandidate"]["Next"] == "StrictMdmActivate"
    assert states["StrictMdmActivate"]["Next"] == "StrictMdmVerify"
    assert states["StrictMdmVerify"]["Next"] == "StrictGoldRefresh"

    insider_cmd = states["StrictInsiderCoverage"]["Parameters"]["Overrides"][
        "ContainerOverrides"
    ][0]["Command.$"]
    assert "'verify-insider-coverage'" in insider_cmd
    assert "'--output'" in insider_cmd
    assert "insider_coverage.json" in insider_cmd
    assert "warehouse-bucket" in insider_cmd
    reconcile_cmd = states["ReconcileRelationshipRelease"]["Parameters"]["Overrides"][
        "ContainerOverrides"
    ][0]["Command.$"]
    assert "'--insider-coverage'" in reconcile_cmd
    assert "insider_coverage.json" in reconcile_cmd

    # sync-graph/verify-graph/graph-activate all target the SAME
    # execution-scoped generation-id -- StrictMdmSyncIdempotency's second
    # sync-graph call is a real idempotency check (same generation, not a
    # fresh random one), and the candidate verified by StrictMdmVerifyCandidate
    # is the exact one StrictMdmActivate activates.
    for state_name in (
        "StrictMdmSync",
        "StrictMdmSyncIdempotency",
        "StrictMdmVerifyCandidate",
        "StrictMdmActivate",
    ):
        cmd = states[state_name]["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
        assert "'--generation-id'" in cmd, (state_name, cmd)
        assert "$$.Execution.Name" in cmd, (state_name, cmd)

    # GRAPH_APP_NODES/GRAPH_APP_EDGES (and the Native App capability checks
    # built on them) are scoped to whatever generation is currently ACTIVE,
    # not to --generation-id's candidate -- verified empirically 2026-07-23.
    # StrictMdmVerifyCandidate must skip them (parity-only candidate gate) or
    # a first-ever activation can never pass. StrictMdmVerify (post-activation,
    # checks the now-active generation) must run them for real.
    candidate_cmd = states["StrictMdmVerifyCandidate"]["Parameters"]["Overrides"][
        "ContainerOverrides"
    ][0]["Command.$"]
    assert "'--skip-native-app'" in candidate_cmd
    final_verify_cmd = states["StrictMdmVerify"]["Parameters"]["Overrides"][
        "ContainerOverrides"
    ][0]["Command.$"]
    assert "'--skip-native-app'" not in final_verify_cmd
    reconcile_cmd = states["ReconcileRelationshipRelease"]["Parameters"][
        "Overrides"
    ]["ContainerOverrides"][0]["Command.$"]
    assert "'reconcile-relationship-release'" in reconcile_cmd
    assert "'--attestations-json'" in reconcile_cmd
    assert "States.JsonToString($.attestations)" in reconcile_cmd
    assert "'--execution-arn'" in reconcile_cmd
    assert "$$.Execution.Id" in reconcile_cmd


def test_seed_from_bronze_and_compute_remaining_batches_preserve_resume_from_run_id(
    tmp_path: Path,
) -> None:
    """Regression test for a live production failure (2026-08-18).

    BatchSilver's ItemSelector references "$.resume_from_run_id" directly
    (a JSONPath reference, not a Choice IsPresent check -- see
    ResumeFromRunIdPresenceCheck/Default above it in the state machine,
    which guarantee the key exists by the time either SeedFromBronze or
    ComputeRemainingBatches runs). ecs_state()'s default ResultPath
    (omitted, meaning "$") REPLACES the entire state input with the ECS
    task's own runTask.sync output on both of these paths, discarding
    resume_from_run_id before BatchSilver ever sees it. A real
    bronze_seed_silver_gold execution failed on exactly this
    (States.ItemReaderFailed: "$.resume_from_run_id ... could not be
    found") the first time this code path actually ran end-to-end,
    because nothing asserted it. Both states must set ResultPath: None to
    preserve $ unchanged, matching the same pattern already used by every
    other "do work but keep $ for a later state" ecs_state() call in this
    file (seed, mdm_seed_universe, compute_windows, fetch_adv_bulk,
    run_wh, compute_identity_refresh_window, etc.).
    """
    definition = _definition(tmp_path)
    states = definition["States"]

    assert states["SeedFromBronze"]["ResultPath"] is None
    assert states["ComputeRemainingBatches"]["ResultPath"] is None
