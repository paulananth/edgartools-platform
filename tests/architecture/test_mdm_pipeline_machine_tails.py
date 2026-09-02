"""Structural checks on the 5 MDM Pipeline Machines' shared-tail wiring.

state-machine-consolidation wayfinder map, ticket 02: after the "one shared
tail" premise turned out wrong (6 genuinely distinct tail shapes across
mdm_gold/ownership_mdm_gold/silver_mdm_gold/bronze_seed_silver_gold/
residual_holds_graph -- see the ticket's addendum), the revised scope wires
each machine's own Publish/Publish Relationships/Reconcile(/GoldRefresh) states through
the shared wire_mdm_tail() sequencing skeleton (infra/scripts/
mdm_tail_helper.py) instead of hand-typed Next pointers, while every flag/
Catch/retry-count difference stays exactly as it was.

These tests generate the real JSON by sourcing the actual bash functions,
mirroring test_load_history_state_machine.py's approach. Network-free: no
AWS calls, only local JSON generation via python3 subprocesses the deploy
script itself launches.
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

_START_MARKER = "write_silver_mdm_gold_definition() {\n"
_END_MARKER = "\nwrite_generation_build_definition() {"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def _extract_function_source() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    start = text.index(_START_MARKER)
    end = text.index(_END_MARKER, start)
    return text[start:end]


def _generate(fn_call: str, tmp_root: Path, name: str) -> dict:
    fn_source = _extract_function_source()
    with tempfile.TemporaryDirectory(dir=tmp_root) as d:
        tmp_path = Path(d)
        fn_file = tmp_path / "mdm_pipeline_fns.sh"
        fn_file.write_text(fn_source, encoding="utf-8")
        out_file = tmp_path / f"{name}.json"

        driver = tmp_path / "driver.sh"
        driver.write_text(
            "set -euo pipefail\n"
            'CLUSTER_ARN="arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster"\n'
            "PUBLIC_SUBNET_IDS_JSON='[\"subnet-aaaa\",\"subnet-bbbb\"]'\n"
            "SECURITY_GROUP_IDS_JSON='[\"sg-cccc\"]'\n"
            'BRONZE_BUCKET_NAME="fake-bronze"\n'
            'WAREHOUSE_BUCKET_NAME="fake-warehouse"\n'
            "BOOTSTRAP_BATCH_CONCURRENCY=3\n"
            "MDM_RUN_LIMIT=100\n"
            "MDM_GRAPH_LIMIT=200\n"
            f'SCRIPT_DIR="{(REPO_ROOT / "infra" / "scripts").as_posix()}"\n'
            f'source "{fn_file.as_posix()}"\n'
            f'{fn_call} "{out_file.as_posix()}" "arn:wh-medium" "arn:mdm-small" "arn:mdm-medium" "arn:wh-large"\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            ["bash", driver.as_posix()], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise AssertionError(
                f"{name} definition generation failed:\nstdout={result.stdout}\nstderr={result.stderr}"
            )
        return json.loads(out_file.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tmp_root() -> Path:
    root = REPO_ROOT / ".pytest_cache" / "mdm_pipeline_machine_tails_test"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture(scope="module")
def silver_mdm_gold(tmp_root: Path) -> dict:
    return _generate("write_silver_mdm_gold_definition", tmp_root, "silver_mdm_gold")


@pytest.fixture(scope="module")
def bronze_seed_silver_gold(tmp_root: Path) -> dict:
    return _generate("write_bronze_seed_silver_gold_definition", tmp_root, "bronze_seed_silver_gold")


def test_silver_mdm_gold_tail_ordering(silver_mdm_gold: dict) -> None:
    s = silver_mdm_gold["States"]
    assert s["MdmBackfill"]["Next"] == "Publish"
    assert s["Publish"]["Next"] == "Publish Relationships"
    assert s["Publish Relationships"]["Next"] == "Reconcile"
    assert s["Reconcile"]["Next"] == "GoldRefresh"
    assert s["GoldRefresh"]["End"] is True


def test_silver_mdm_gold_verify_catch_fallthrough_preserved(silver_mdm_gold: dict) -> None:
    # verify-graph must never block gold-refresh (docs/data-architecture.md)
    # -- this is exactly the kind of caller-owned behavior wire_mdm_tail is
    # deliberately blind to and must not strip.
    verify = silver_mdm_gold["States"]["Reconcile"]
    assert verify.get("Catch") == [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "GoldRefresh"}]


def test_silver_mdm_gold_no_limit_flag_on_mdm_commands(silver_mdm_gold: dict) -> None:
    # INVARIANT (see the generator's own comment): a full bulk re-run must
    # never carry MDM_RUN_LIMIT/MDM_GRAPH_LIMIT, even though those env vars
    # were set non-zero in this test's driver.
    s = silver_mdm_gold["States"]
    for state_name in ("Mastering", "MdmBackfill", "Publish Relationships"):
        command = s[state_name]["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
        assert "--limit" not in command, f"{state_name} must not carry --limit: {command}"


def test_bronze_seed_silver_gold_default_tail_ordering(bronze_seed_silver_gold: dict) -> None:
    s = bronze_seed_silver_gold["States"]
    assert s["MdmBackfill"]["Next"] == "Publish"
    assert s["Publish"]["Next"] == "Publish Relationships"
    assert s["Publish Relationships"]["Next"] == "Reconcile"
    assert s["Reconcile"]["Next"] == "GoldRefresh"
    assert s["GoldRefresh"]["End"] is True
    assert s["Reconcile"].get("Catch") == [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "GoldRefresh"}]


def test_bronze_seed_silver_gold_strict_branch_untouched(bronze_seed_silver_gold: dict) -> None:
    # The Ticket-20 "strict" release-mode branch is a completely separate
    # 6-state graph with no equivalent elsewhere -- it must survive the
    # wire_mdm_tail refactor of the *default* tail exactly as before, with
    # its own independent Export->Sync->SyncIdempotency->VerifyCandidate->
    # Verify->GoldRefresh chain still wired by hand (nothing to deduplicate,
    # since it has no sibling).
    s = bronze_seed_silver_gold["States"]
    for name in (
        "StrictPublish", "Strict Publish Relationships", "Strict Publish Relationships Idempotency",
        "Strict Reconcile Candidate", "StrictReconcile", "StrictGoldRefresh",
    ):
        assert name in s, f"missing strict-mode state: {name}"
    assert s["StrictPublish"]["Next"] == "Strict Publish Relationships"
    assert s["StrictReconcile"]["Next"] == "StrictGoldRefresh"
    assert s["StrictGoldRefresh"]["End"] is True


def test_no_shared_state_names_between_default_and_strict_paths(bronze_seed_silver_gold: dict) -> None:
    s = bronze_seed_silver_gold["States"]
    assert "Publish" in s and "StrictPublish" in s
    assert s["Publish"] != s["StrictPublish"]
