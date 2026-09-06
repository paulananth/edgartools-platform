"""Structural checks on the remaining MDM Pipeline Machines' shared-tail wiring.

state-machine-consolidation wayfinder map, ticket 02: after the "one shared
tail" premise turned out wrong (6 genuinely distinct tail shapes across
mdm_gold/ownership_mdm_gold/silver_mdm_gold/one_click_data_refresh/
residual_holds_graph -- see the ticket's addendum), the revised scope wires
each machine's own Publish/Publish Relationships/Reconcile(/"Publish Business
Data") states through
the shared wire_mdm_tail() sequencing skeleton (infra/scripts/
mdm_tail_helper.py) instead of hand-typed Next pointers, while every flag/
Catch/retry-count difference stays exactly as it was.

mdm_gold retired by ticket 07 (deleted outright -- it had no head, fully
redundant with the new single MDM machine); ownership_mdm_gold retired
separately (own ticket, predates this file's last update); silver_mdm_gold
retired by ticket 09 (2026-09-05: zero executions ever -- deleted outright,
not modified, so it has no tests here anymore). Ticket 09 also confirmed
one_click_data_refresh's default path is NOT dead (install.sh's documented
cold-start/recovery procedure depends on it) -- deferred, untouched. Only 2
machines still use wire_mdm_tail() as-is: one_click_data_refresh's default
path (this file) and residual_holds_graph (its own test file).

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

_START_MARKER = "write_one_click_data_refresh_definition() {\n"
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
def one_click_data_refresh(tmp_root: Path) -> dict:
    return _generate("write_one_click_data_refresh_definition", tmp_root, "one_click_data_refresh")


def test_one_click_data_refresh_default_tail_ordering(one_click_data_refresh: dict) -> None:
    s = one_click_data_refresh["States"]
    assert s["Infer Relationships"]["Next"] == "Publish"
    assert s["Publish"]["Next"] == "Publish Relationships"
    assert s["Publish Relationships"]["Next"] == "Reconcile"
    assert s["Reconcile"]["Next"] == "Publish Business Data"
    assert s["Publish Business Data"]["End"] is True
    assert s["Reconcile"].get("Catch") == [{"ErrorEquals": ["States.ALL"], "ResultPath": None, "Next": "Publish Business Data"}]


def test_one_click_data_refresh_strict_branch_untouched(one_click_data_refresh: dict) -> None:
    # The Ticket-20 "strict" release-mode branch is a completely separate
    # 6-state graph with no equivalent elsewhere -- it must survive the
    # wire_mdm_tail refactor of the *default* tail exactly as before, with
    # its own independent Export->Sync->SyncIdempotency->VerifyCandidate->
    # Verify->"Strict Publish Business Data" chain still wired by hand
    # (nothing to deduplicate, since it has no sibling).
    s = one_click_data_refresh["States"]
    for name in (
        "StrictPublish", "Strict Publish Relationships", "Strict Publish Relationships Idempotency",
        "Strict Reconcile Candidate", "StrictReconcile", "Strict Publish Business Data",
    ):
        assert name in s, f"missing strict-mode state: {name}"
    assert s["StrictPublish"]["Next"] == "Strict Publish Relationships"
    assert s["StrictReconcile"]["Next"] == "Strict Publish Business Data"
    assert s["Strict Publish Business Data"]["End"] is True


def test_no_shared_state_names_between_default_and_strict_paths(one_click_data_refresh: dict) -> None:
    s = one_click_data_refresh["States"]
    assert "Publish" in s and "StrictPublish" in s
    assert s["Publish"] != s["StrictPublish"]
