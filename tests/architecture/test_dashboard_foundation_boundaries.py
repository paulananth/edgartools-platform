from __future__ import annotations

import importlib.util
import re
import sys
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


class _FakeCacheData:
    def __call__(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def clear(self) -> None:
        return None


class _FakeStreamlit:
    def __init__(self) -> None:
        self.cache_data = _FakeCacheData()
        self.dataframes: list[list[dict[str, object]]] = []

    def subheader(self, *_args, **_kwargs) -> None:
        return None

    def bar_chart(self, *_args, **_kwargs) -> None:
        return None

    def dataframe(self, rows, *_args, **_kwargs) -> None:
        self.dataframes.append(rows)


def _load_streamlit_app_with_fake_streamlit() -> tuple[object, _FakeStreamlit]:
    target = REPO_ROOT / "examples" / "mdm_graph_dashboard" / "streamlit_app.py"
    fake_streamlit = _FakeStreamlit()
    spec = importlib.util.spec_from_file_location(
        "_phase9_streamlit_app_under_test",
        target,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load streamlit_app.py")
    module = importlib.util.module_from_spec(spec)
    original_streamlit = sys.modules.get("streamlit")
    sys.modules["streamlit"] = fake_streamlit
    try:
        spec.loader.exec_module(module)
    finally:
        if original_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = original_streamlit
    return module, fake_streamlit


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

    def test_streamlit_graph_queries_use_full_registry_not_bounded_samples(self) -> None:
        target = REPO_ROOT / "examples" / "mdm_graph_dashboard" / "streamlit_app.py"
        if not target.exists():
            self.skipTest("streamlit_app.py not created yet")
        text = _read(target)
        self.assertIn("_relationship_types_from_mdm_metrics", text)
        self.assertIn("_entity_labels_from_mdm_metrics", text)
        self.assertIn("neo4j_labels", text)
        self.assertNotIn("_relationship_types_from_diagnostics", text)
        self.assertNotIn("_entity_labels_from_diagnostics", text)
        self.assertNotIn("known_mdm_edge_keys", text)

    @unittest.expectedFailure
    def test_entity_comparison_uses_registry_labels_for_neo4j_node_counts(self) -> None:
        """Escalated GRAPH-01 regression: current UI uses plural label stripping."""
        module, fake_streamlit = _load_streamlit_app_with_fake_streamlit()

        module._render_entity_comparison(
            mdm_metrics={
                "available": True,
                "entity_counts": {
                    "company": {"label": "Companies", "count": 3},
                    "security": {"label": "Securities", "count": 4},
                    "person": {"label": "People", "count": 5},
                },
                "registry": {
                    "entity_type_details": [
                        {"entity_type": "company", "neo4j_label": "Company"},
                        {"entity_type": "security", "neo4j_label": "Security"},
                        {"entity_type": "person", "neo4j_label": "Person"},
                    ]
                },
            },
            neo4j_metrics={
                "available": True,
                "node_counts": {
                    "Company": {"node_count": 30},
                    "Security": {"node_count": 40},
                    "Person": {"node_count": 50},
                },
            },
        )

        detail_rows = fake_streamlit.dataframes[-1]
        neo4j_counts = {
            str(row["Domain"]): row["Neo4j Count"]
            for row in detail_rows
        }
        self.assertEqual(
            neo4j_counts,
            {
                "Companies": 30,
                "Securities": 40,
                "People": 50,
            },
        )
