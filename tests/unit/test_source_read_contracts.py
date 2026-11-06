"""Every contract a `source.read` step names passes the worker's own checks.

A contract the worker refuses stops a real load on its first file, and nothing
else reads the file before then.
"""
from pathlib import Path

import pytest

from edgar_warehouse.rules import files
from edgar_warehouse.workers import source_read

SOURCES = Path(__file__).resolve().parents[2] / "rules" / "sources"


def _contracts():
    for rule in sorted(SOURCES.glob("*/source.yaml")):
        targets = (files.loads(rule.read_text()).get("bookkeeping") or {}).get("targets", {})
        for target, body in targets.items():
            for step in body.get("steps", []):
                named = step.get("input") if isinstance(step.get("input"), dict) else {}
                if step.get("operation") == "source.read" and "contract" in named:
                    beside = rule.parent / named["contract"]
                    path = beside if beside.exists() else SOURCES / named["contract"]
                    yield pytest.param(path, id=f"{rule.parent.name}-{target}-{step['name']}")


@pytest.mark.parametrize("path", _contracts())
def test_the_worker_accepts_the_contract(path):
    contract = files.loads(path.read_text())
    execution = source_read.execution_of(contract)
    if "stream" not in contract["read"]:
        source_read.limits(contract, execution)
