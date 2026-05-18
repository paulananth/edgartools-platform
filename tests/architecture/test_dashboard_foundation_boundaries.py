from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE8_TARGETS = [
    REPO_ROOT / "examples" / "mdm_graph_dashboard" / "streamlit_app.py",
    REPO_ROOT / "examples" / "mdm_graph_dashboard" / "README.md",
    REPO_ROOT / "edgar_warehouse" / "mdm" / "dashboard_readonly.py",
    REPO_ROOT / "edgar_warehouse" / "mdm" / "graph_readonly.py",
]
DASHBOARD_TEXT_TARGETS = [
    REPO_ROOT / "examples" / "mdm_graph_dashboard" / "streamlit_app.py",
    REPO_ROOT / "examples" / "mdm_graph_dashboard" / "README.md",
]


def _existing(paths: list[Path]) -> list[Path]:
    return [path for path in paths if path.exists()]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class DashboardFoundationBoundaryTests(unittest.TestCase):
    def test_phase8_targets_do_not_import_mutation_surfaces(self) -> None:
        forbidden = [
            "MDMPipeline",
            "GraphSyncEngine",
            "migrations.runtime",
            "edgar_warehouse.mdm.resolvers",
            "edgar_warehouse.mdm.stewardship",
            "relationship_merge_cypher",
            "node_merge_cypher",
            "backfill_relationship_instances",
            "_handle_run",
            "_handle_migrate",
            "_handle_sync_graph",
            "_handle_derive_relationships",
            "_handle_load_relationships",
        ]
        offenders = {
            path.relative_to(REPO_ROOT): token
            for path in _existing(PHASE8_TARGETS)
            for token in forbidden
            if token in _read(path)
        }
        self.assertEqual(offenders, {})

    def test_graph_readonly_contains_no_write_cypher_tokens(self) -> None:
        target = REPO_ROOT / "edgar_warehouse" / "mdm" / "graph_readonly.py"
        if not target.exists():
            self.skipTest("graph_readonly.py not created yet")
        text = _read(target)
        offenders = [
            token
            for token in ("MERGE", "CREATE", "DELETE", "SET", "REMOVE", "CALL")
            if re.search(rf"\b{token}\b", text)
        ]
        self.assertEqual(offenders, [])

    def test_dashboard_text_contains_no_mutation_controls(self) -> None:
        forbidden_labels = [
            "sync graph",
            "derive relationships",
            "load relationships",
            "migrate",
            "seed universe",
            "merge",
            "quarantine",
            "accept",
            "reject",
        ]
        offenders = {
            path.relative_to(REPO_ROOT): label
            for path in _existing(DASHBOARD_TEXT_TARGETS)
            for label in forbidden_labels
            if label in _read(path).lower()
        }
        self.assertEqual(offenders, {})

    def test_dashboard_text_avoids_out_of_scope_paths(self) -> None:
        forbidden_paths = [
            "infra/aws-dev-application.json",
            "infra/aws-prod-application.json",
            "infra/terraform",
            "step functions",
            "deploy-aws-application.sh",
            "publish-warehouse-image.sh",
            "infra/snowflake/dbt",
            "edgar_universe_dashboard.py",
        ]
        offenders = {
            path.relative_to(REPO_ROOT): token
            for path in _existing(DASHBOARD_TEXT_TARGETS)
            for token in forbidden_paths
            if token in _read(path).lower()
        }
        self.assertEqual(offenders, {})

    def test_streamlit_shell_uses_readonly_helpers_only(self) -> None:
        target = REPO_ROOT / "examples" / "mdm_graph_dashboard" / "streamlit_app.py"
        if not target.exists():
            self.skipTest("streamlit_app.py not created yet")
        text = _read(target)
        self.assertIn("dashboard_readonly", text)
        self.assertIn("graph_readonly", text)
        self.assertNotIn("SELECT ", text.upper())
        self.assertNotIn("RETURN 1 AS ok", text)
