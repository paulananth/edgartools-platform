from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE9_TARGETS = [
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
    def test_phase9_targets_include_dashboard_and_readonly_helpers(self) -> None:
        expected = {
            "examples/mdm_graph_dashboard/streamlit_app.py",
            "examples/mdm_graph_dashboard/README.md",
            "edgar_warehouse/mdm/dashboard_readonly.py",
            "edgar_warehouse/mdm/graph_readonly.py",
        }
        actual = {path.relative_to(REPO_ROOT).as_posix() for path in PHASE9_TARGETS}
        self.assertEqual(actual, expected)

    def test_phase9_targets_do_not_import_mutation_surfaces(self) -> None:
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
            for path in _existing(PHASE9_TARGETS)
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

    def test_streamlit_contains_no_raw_sql_or_cypher(self) -> None:
        target = REPO_ROOT / "examples" / "mdm_graph_dashboard" / "streamlit_app.py"
        if not target.exists():
            self.skipTest("streamlit_app.py not created yet")
        text = _read(target)
        self.assertNotRegex(text.upper(), r"\bSELECT\s")
        self.assertNotRegex(text.upper(), r"\bMATCH\s")
        self.assertNotIn("RETURN 1 AS ok", text)

    def test_dashboard_text_contains_no_mutation_controls(self) -> None:
        forbidden_labels = {
            "sync",
            "derive",
            "load",
            "migrate",
            "seed",
            "merge",
            "repair",
            "quarantine",
            "accept",
            "reject",
            "edit",
            "delete",
            "credential",
        }
        control_patterns = (
            r"st\.(?:button|link_button|download_button|checkbox|toggle|radio|"
            r"selectbox|multiselect|text_input|text_area)"
            r"\([^)]*['\"]([^'\"]+)['\"]"
        )
        command_patterns = (
            r"(?:uv run|edgar-warehouse|aws |terraform |dbt |bash )[^`\n]*"
            r"(sync|derive|load|migrate|seed|merge|repair|quarantine|accept|"
            r"reject|edit|delete)"
        )
        offenders = {
            path.relative_to(REPO_ROOT): match.group(0)
            for path in _existing(DASHBOARD_TEXT_TARGETS)
            for match in re.finditer(control_patterns, _read(path), flags=re.IGNORECASE)
            if any(label in match.group(1).lower() for label in forbidden_labels)
        }
        command_offenders = {
            path.relative_to(REPO_ROOT): match.group(0)
            for path in _existing(DASHBOARD_TEXT_TARGETS)
            for match in re.finditer(command_patterns, _read(path).lower())
        }
        self.assertEqual(offenders | command_offenders, {})

    def test_dashboard_text_avoids_out_of_scope_paths(self) -> None:
        forbidden_paths = [
            "infra/aws-dev-application.json",
            "infra/aws-prod-application.json",
            "infra/terraform",
            "step functions",
            "deploy-aws-application.sh",
            "publish-warehouse-image.sh",
            "infra/snowflake/dbt",
            "snowflake",
            "dbt",
            "terraform",
            "generated application json",
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
        self.assertIn("dashboard_readonly.get_mdm_dashboard_metrics", text)
        self.assertIn("dashboard_readonly.get_active_relationship_diagnostic_inputs", text)
        self.assertIn("graph_readonly.get_neo4j_graph_metrics", text)
