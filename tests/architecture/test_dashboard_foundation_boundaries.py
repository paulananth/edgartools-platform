from __future__ import annotations

import importlib.util
import re
import sys
import types
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


def _dashboard_source() -> str:
    return _read(REPO_ROOT / "examples" / "mdm_graph_dashboard" / "streamlit_app.py")


def _dashboard_readme() -> str:
    return _read(REPO_ROOT / "examples" / "mdm_graph_dashboard" / "README.md")


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
    fake_dashboard_readonly = types.ModuleType("edgar_warehouse.mdm.dashboard_readonly")
    fake_graph_readonly = types.ModuleType("edgar_warehouse.mdm.graph_readonly")
    fake_dashboard_readonly.get_mdm_dashboard_metrics = lambda: None
    fake_dashboard_readonly.get_active_relationship_diagnostic_inputs = lambda: None
    fake_dashboard_readonly.build_relationship_coverage_rows = lambda *_args, **_kwargs: []
    fake_graph_readonly.get_neo4j_graph_metrics = lambda *_args, **_kwargs: None
    spec = importlib.util.spec_from_file_location(
        "_phase9_streamlit_app_under_test",
        target,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load streamlit_app.py")
    module = importlib.util.module_from_spec(spec)
    original_streamlit = sys.modules.get("streamlit")
    original_dashboard_readonly = sys.modules.get("edgar_warehouse.mdm.dashboard_readonly")
    original_graph_readonly = sys.modules.get("edgar_warehouse.mdm.graph_readonly")
    sys.modules["streamlit"] = fake_streamlit
    sys.modules["edgar_warehouse.mdm.dashboard_readonly"] = fake_dashboard_readonly
    sys.modules["edgar_warehouse.mdm.graph_readonly"] = fake_graph_readonly
    try:
        spec.loader.exec_module(module)
    finally:
        if original_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = original_streamlit
        if original_dashboard_readonly is None:
            sys.modules.pop("edgar_warehouse.mdm.dashboard_readonly", None)
        else:
            sys.modules["edgar_warehouse.mdm.dashboard_readonly"] = original_dashboard_readonly
        if original_graph_readonly is None:
            sys.modules.pop("edgar_warehouse.mdm.graph_readonly", None)
        else:
            sys.modules["edgar_warehouse.mdm.graph_readonly"] = original_graph_readonly
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
        self.assertTrue(target.exists(), "graph_readonly.py must exist for hosted graph dashboard reads")
        text = _read(target)
        offenders = [
            token
            for token in ("MERGE", "CREATE", "DELETE", "SET", "REMOVE", "CALL")
            if re.search(rf"\b{token}\b", text)
        ]
        self.assertEqual(offenders, [])

    def test_graph_readonly_avoids_cli_subprocess_and_external_neo4j_dependencies(self) -> None:
        target = REPO_ROOT / "edgar_warehouse" / "mdm" / "graph_readonly.py"
        self.assertTrue(target.exists(), "graph_readonly.py must exist for hosted graph dashboard reads")
        text = _read(target)

        forbidden = [
            "subprocess",
            "edgar_warehouse.mdm.cli",
            "edgar-warehouse",
            "stdout",
            "check_output",
            "popen",
            "NEO4J_URI",
            "NEO4J_USER",
            "NEO4J_PASSWORD",
            "NEO4J_DATABASE",
            "NEO4J_SECRET_JSON",
            "bolt://",
            "neo4j://",
            "Aura",
        ]
        offenders = {token for token in forbidden if token in text}
        self.assertEqual(offenders, set())

    def test_graph_readonly_exposes_hosted_snowflake_dashboard_contract(self) -> None:
        target = REPO_ROOT / "edgar_warehouse" / "mdm" / "graph_readonly.py"
        self.assertTrue(target.exists(), "graph_readonly.py must exist for hosted graph dashboard reads")
        text = _read(target)

        for token in (
            "get_snowflake_graph_metrics",
            "SnowflakeGraphVerifier",
            "SnowflakeGraphVerificationConfig",
            "entity_comparison",
            "relationship_comparison",
            "missing_graph_edge_endpoints",
            "failing_checks",
            "SNOWFLAKE_GRAPH_UNAVAILABLE_MESSAGE",
            "SNOWFLAKE_GRAPH_PERMISSION_DENIED_MESSAGE",
        ):
            self.assertIn(token, text)

    def test_streamlit_contains_no_raw_sql_or_cypher(self) -> None:
        target = REPO_ROOT / "examples" / "mdm_graph_dashboard" / "streamlit_app.py"
        if not target.exists():
            self.skipTest("streamlit_app.py not created yet")
        text = _read(target)
        query_scan_text = (
            text.replace("No rows match the current filters.", "")
            .replace(
                "MDM database permission denied. Confirm the configured database user can run read-only SELECT queries.",
                "",
            )
            .replace(
                "Neo4j permission denied. Confirm the configured graph user can run read-only MATCH queries.",
                "",
            )
        )
        self.assertNotRegex(query_scan_text.upper(), r"\bSELECT\s")
        self.assertNotRegex(query_scan_text.upper(), r"\bMATCH\s")
        self.assertNotIn("RETURN 1 AS ok", query_scan_text)

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

    def test_entity_comparison_uses_registry_labels_for_neo4j_node_counts(self) -> None:
        """GRAPH-01 regression: entity coverage uses registry Neo4j labels."""
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

    def test_phase10_navigation_labels_are_final_operator_views(self) -> None:
        module, _fake_streamlit = _load_streamlit_app_with_fake_streamlit()

        self.assertEqual(
            module.SECTIONS,
            [
                "Overview",
                "MDM Overview",
                "Neo4j Overview",
                "Mismatch Diagnostics",
            ],
        )
        self.assertNotIn("Entities", module.SECTIONS)
        self.assertNotIn("Relationships", module.SECTIONS)
        self.assertNotIn("Graph Coverage", module.SECTIONS)
        self.assertNotIn("Neighborhood", module.SECTIONS)

    def test_overview_renders_attention_before_snapshot_metrics(self) -> None:
        text = _dashboard_source()
        render_overview = text.split("def render_overview(", 1)[1].split("\ndef ", 1)[0]

        self.assertLess(
            render_overview.index("_render_grouped_warnings"),
            render_overview.index("_render_snapshot"),
        )

    def test_row_limit_choices_and_default_are_bounded(self) -> None:
        text = _dashboard_source()

        self.assertIn("ROW_LIMIT_OPTIONS = [25, 50, 100, 250]", text)
        self.assertRegex(
            text,
            r"st\.sidebar\.selectbox\(\s*['\"]Row limit['\"],\s*ROW_LIMIT_OPTIONS,\s*index=1",
        )

    def test_page_filters_are_single_select_with_all_default(self) -> None:
        text = _dashboard_source()

        self.assertIn('FILTER_ALL = "All"', text)
        self.assertRegex(text, r"st\.selectbox\(\s*['\"]Entity type['\"].*index=0")
        self.assertRegex(text, r"st\.selectbox\(\s*['\"]Relationship type['\"].*index=0")
        for forbidden in (
            "st.text_input",
            "st.text_area",
            "st.number_input",
            "st.multiselect",
            "st.checkbox",
            "st.toggle",
        ):
            self.assertNotIn(forbidden, text)

    def test_filtered_empty_copy_is_exact(self) -> None:
        text = _dashboard_source()

        self.assertIn("No rows match the current filters.", text)

    def test_d09_d10_d11_d12_state_copy_is_exact_and_secret_safe(self) -> None:
        text = _dashboard_source()
        expected_copy = [
            "MDM configuration is required. Set `MDM_DATABASE_URL`, then restart the dashboard.",
            "MDM database unavailable. Check `MDM_DATABASE_URL`, confirm the database is reachable, and restart the dashboard.",
            "Neo4j graph metrics unavailable. MDM overview remains available.",
            "Neo4j permission denied. Confirm the configured graph user can run read-only MATCH queries.",
            "No rows match the current filters.",
            "Adjust the selected type or row limit, then review the table again.",
        ]

        for copy in expected_copy:
            self.assertIn(copy, text)

        for unsafe_token in (
            "password=",
            "postgresql://",
            "neo4j://",
            "bolt://",
            "example.internal",
            "traceback",
            "RuntimeError(",
        ):
            self.assertNotIn(unsafe_token, text)

    def test_d13_d14_d15_d16_readme_contract_matches_operator_runbook(self) -> None:
        text = _dashboard_readme()
        headings = re.findall(r"^## (.+)$", text, flags=re.MULTILINE)

        self.assertEqual(
            headings,
            [
                "Purpose",
                "Read-only guarantee",
                "Prerequisites",
                "Launch",
                "Review workflow",
                "Filters",
                "Failure states",
                "Existing checks",
                "Validation",
            ],
        )
        self.assertIn(
            "This dashboard does not run sync, repair, migrate, load, or write actions.",
            text,
        )
        for env_var in (
            "MDM_DATABASE_URL",
            "NEO4J_URI",
            "NEO4J_USER",
            "NEO4J_PASSWORD",
            "NEO4J_DATABASE",
            "NEO4J_SECRET_JSON",
        ):
            self.assertIn(env_var, text)

        self.assertIn("Overview", text)
        self.assertIn("MDM Overview", text)
        self.assertIn("Neo4j Overview", text)
        self.assertIn("Mismatch Diagnostics", text)
        self.assertIn("Row limit", text)
        self.assertIn("25", text)
        self.assertIn("50", text)
        self.assertIn("100", text)
        self.assertIn("250", text)
        self.assertIn("All", text)

        allowed_commands = {
            "edgar-warehouse mdm check-connectivity --neo4j",
            "edgar-warehouse mdm counts",
            "edgar-warehouse mdm verify-graph",
        }
        mdm_commands = set(
            re.findall(r"^edgar-warehouse mdm [^\n`]+$", text, flags=re.MULTILINE)
        )
        self.assertEqual(mdm_commands, allowed_commands)
        self.assertIn(
            "uv run pytest tests/mdm/test_dashboard_readonly.py tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py -q",
            text,
        )

        lowered = text.lower()
        for forbidden in (
            "visible sections",
            "manual browser checklist",
            "remediation button",
            "dashboard button",
            "dashboard control",
            "sync button",
            "repair button",
            "migrate button",
            "load button",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_aws_mdm_e2e_uses_hosted_graph_validation_gate(self) -> None:
        text = _read(REPO_ROOT / "infra" / "scripts" / "run-aws-mdm-e2e.sh")

        self.assertIn("AWS-only MDM hosted graph e2e", text)
        self.assertIn("Snowflake-hosted graph validation", text)
        self.assertNotIn('start_and_wait "mdm_check_connectivity"', text)
        self.assertIn('start_and_wait "mdm_sync_graph"', text)
        self.assertIn('start_and_wait "mdm_verify_graph"', text)
        self.assertIn("warn_lingering_neo4j_references", text)
        self.assertIn("WARNING", text)
        self.assertIn("NEO4J_*", text)
        self.assertIn("--snow-connection", text)
        self.assertIn("--snowflake-database", text)
        self.assertIn("--native-app-compute-pool", text)
        self.assertIn("--skip-preflight", text)
        self.assertIn("run_hosted_graph_preflight", text)
        self.assertIn("uv run --extra snowflake edgar-warehouse mdm verify-graph", text)
        self.assertIn("SNOWFLAKE_CONNECTION=${SNOW_CONNECTION_NAME}", text)
        self.assertIn("DBT_SNOWFLAKE_DATABASE=${SNOWFLAKE_DATABASE_NAME}", text)
        self.assertIn("MDM_SNOWFLAKE_DATABASE=${SNOWFLAKE_DATABASE_NAME}", text)

        status_only_block = text.index('if [[ "$RUN_E2E" != "true" ]]; then')
        preflight_call = text.rindex("run_hosted_graph_preflight")
        self.assertLess(status_only_block, preflight_call)
