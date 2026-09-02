"""Structural checks on residual_holds_graph's tail (no GoldRefresh).

state-machine-consolidation wayfinder map, ticket 02: residual_holds_graph
is the one MDM Pipeline Machine with no GoldRefresh at all (it does not
claim Ticket 20 GO) and its own generation-scoped Publish Relationships/Reconcile flags
(--generation-id, --skip-native-app). This is the
highest-risk of the three inline (non-function) MDM Pipeline Machine
blocks for wire_mdm_tail's gold_state=None path.

residual_holds_graph is generated inline (not via a named bash function)
directly inside deploy-aws-application.sh's main orchestration flow, so
this test extracts its Python heredoc body directly by locating the unique
anchor text around its `python3 - ... <<'PY'` invocation, rather than
sourcing a callable bash function (mirrors the extraction technique other
tests in this repo already use for similar inline blocks).
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

_ANCHOR = '"$residual_holds_graph_file" "$CLUSTER_ARN"'
_HEREDOC_OPEN = "<<'PY'\n"
_HEREDOC_CLOSE = "\nPY\n"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def _extract_python_body() -> str:
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    anchor_pos = text.index(_ANCHOR)
    open_pos = text.index(_HEREDOC_OPEN, anchor_pos) + len(_HEREDOC_OPEN)
    close_pos = text.index(_HEREDOC_CLOSE, open_pos)
    return text[open_pos:close_pos]


@pytest.fixture(scope="module")
def definition() -> dict:
    py_source = _extract_python_body()
    root = REPO_ROOT / ".pytest_cache" / "residual_holds_graph_tail_test"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as d:
        tmp_path = Path(d)
        out_file = tmp_path / "residual_holds_graph.json"
        script_dir = REPO_ROOT / "infra" / "scripts"

        result = subprocess.run(
            [
                "python3", "-",
                out_file.as_posix(),
                "arn:aws:ecs:us-east-1:000000000000:cluster/fake-cluster",
                "arn:mdm-small", "arn:mdm-large",
                "edgar-warehouse",
                '["subnet-aaaa","subnet-bbbb"]',
                '["sg-cccc"]',
                script_dir.as_posix(),
            ],
            input=py_source,
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode != 0:
            raise AssertionError(
                f"residual_holds_graph definition generation failed:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        return json.loads(out_file.read_text(encoding="utf-8"))


def test_tail_ordering_with_no_gold_refresh(definition: dict) -> None:
    s = definition["States"]
    assert s["MdmInstitutionalHolds"]["Next"] == "Publish"
    assert s["Publish"]["Next"] == "Publish Relationships"
    assert s["Publish Relationships"]["Next"] == "Reconcile"
    assert s["Reconcile"]["End"] is True
    assert "Next" not in s["Reconcile"]
    assert "GoldRefresh" not in s


def test_sync_carries_generation_id_without_a_completeness_cap(definition: dict) -> None:
    command = definition["States"]["Publish Relationships"]["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "--generation-id" in command
    assert "$$.Execution.Name" in command
    assert "--limit-per-type" not in command


def test_verify_carries_skip_native_app_and_generation_id(definition: dict) -> None:
    command = definition["States"]["Reconcile"]["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    assert "--skip-native-app" in command
    assert "--generation-id" in command


def test_export_uses_mdm_large_task_definition(definition: dict) -> None:
    # OOM safety: heavy stages use mdm-large, not mdm-medium (prod
    # MdmSecurities OOM on 2 GiB, see the generator's own comment).
    assert definition["States"]["Publish"]["Parameters"]["TaskDefinition"] == "arn:mdm-large"
    assert definition["States"]["Reconcile"]["Parameters"]["TaskDefinition"] == "arn:mdm-small"
