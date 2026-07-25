"""Architecture guard for residual_holds_graph (Ticket 20 residual pipeline).

Handoff residual after EMPLOYED_BY bulk-load: security nodes, IS_INSIDER,
HOLDS/COMPANY_HOLDS, and INSTITUTIONAL_HOLDS empty on the graph generation.
This SM must populate those without re-running full company MDM.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

DEPLOY = Path("infra/scripts/deploy-aws-application.sh")


def _extract_residual_definition_source() -> str:
    text = DEPLOY.read_text(encoding="utf-8")
    marker = "residual_holds_graph_file="
    assert marker in text, "residual_holds_graph SM not registered in deploy script"
    # Pull the embedded Python definition block
    start = text.index("# residual_holds_graph:")
    end = text.index("residual_holds_graph_arn=", start)
    return text[start:end]


def test_residual_holds_graph_registered_and_named() -> None:
    src = _extract_residual_definition_source()
    assert "upsert_state_machine residual_holds_graph" in DEPLOY.read_text(encoding="utf-8")
    assert "MdmSecurities" in src
    assert "MdmInstitutionalHolds" in src
    assert "StartAt" in src and "MdmSecurities" in src


def test_residual_holds_graph_does_not_re_run_all_companies() -> None:
    src = _extract_residual_definition_source()
    # No mdm run --entity-type company|all (sync-graph may still list company
    # nodes as materialization targets for endpoint integrity).
    assert re.search(r"mdm',\s*'run',\s*'--entity-type',\s*'company'", src) is None
    assert re.search(r"mdm',\s*'run',\s*'--entity-type',\s*'all'", src) is None
    assert "'run', '--entity-type', 'security'" in src or "entity-type', 'security'" in src


def test_residual_holds_graph_covers_handoff_residual_types() -> None:
    src = _extract_residual_definition_source()
    for rel in ("IS_INSIDER", "HOLDS", "COMPANY_HOLDS", "INSTITUTIONAL_HOLDS"):
        assert rel in src, f"missing relationship type {rel}"
    assert "security" in src
    assert "person" in src
    # OOM-safe separate institutional step
    assert "MdmInstitutionalHolds" in src
    assert "MdmExport" in src
    assert "sync-graph" in src


def test_residual_holds_graph_order() -> None:
    src = _extract_residual_definition_source()
    # Order by first occurrence of state name keys in the definition string
    order = []
    for name in (
        "MdmSecurities",
        "MdmPersons",
        "MdmIsInsider",
        "MdmHolds",
        "MdmCompanyHolds",
        "MdmInstitutionalHolds",
        "MdmExport",
        "MdmSync",
        "MdmVerify",
    ):
        idx = src.find(f'"{name}"')
        assert idx >= 0, f"state {name} missing"
        order.append((idx, name))
    order_names = [n for _, n in sorted(order)]
    assert order_names == [
        "MdmSecurities",
        "MdmPersons",
        "MdmIsInsider",
        "MdmHolds",
        "MdmCompanyHolds",
        "MdmInstitutionalHolds",
        "MdmExport",
        "MdmSync",
        "MdmVerify",
    ]
