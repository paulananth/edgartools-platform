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
        "PUBLIC_SUBNET_IDS_JSON='[\"subnet-1\"]'\n"
        "SECURITY_GROUP_IDS_JSON='[\"sg-1\"]'\n"
        "BOOTSTRAP_BATCH_CONCURRENCY=4\n"
        "MDM_RUN_LIMIT=100\n"
        "MDM_GRAPH_LIMIT=100\n"
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
    assert states["ReleaseModeCheck"]["Default"] == "BatchSizeCheck"
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
    assert strict_map["MaxConcurrency"] == 4
    assert strict_map["ToleratedFailurePercentage"] == 0
    assert strict_map["Next"] == "ReconcileRelationshipRelease"
    command = strict_map["ItemProcessor"]["States"]["RunStrictBatch"]["Parameters"][
        "Overrides"
    ]["ContainerOverrides"][0]["Command.$"]
    assert "'--release-mode'" in command
    assert "'--candidate-manifest'" in command
    assert "branch_b_deferred" in command
    assert "Retry" not in strict_map["ItemProcessor"]["States"]["RunStrictBatch"]
    assert "Catch" not in states["StrictMdmVerify"]
    assert states["StrictMdmBackfill"]["Next"] == "StrictMdmIdempotency"
    assert states["StrictMdmIdempotency"]["Next"] == "StrictMdmExport"
    assert states["StrictMdmSync"]["Next"] == "StrictMdmSyncIdempotency"
    assert states["StrictMdmSyncIdempotency"]["Next"] == "StrictMdmVerify"
    assert states["StrictMdmVerify"]["Next"] == "StrictGoldRefresh"
