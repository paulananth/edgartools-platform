from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
STREAMLIT_APP = REPO_ROOT / "infra" / "snowflake" / "mdm_dashboard" / "streamlit_app.py"


class _FakeCacheData:
    def __call__(self, func=None, *args, **kwargs):
        if func is None:
            return lambda wrapped: wrapped
        return func

    def clear(self) -> None:
        return None


class _FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return False

    def metric(self, *_args, **_kwargs) -> None:
        return None


class _FakeStreamlit:
    cache_data = _FakeCacheData()

    def set_page_config(self, *_args, **_kwargs) -> None:
        return None

    def title(self, *_args, **_kwargs) -> None:
        return None

    def caption(self, *_args, **_kwargs) -> None:
        return None

    def subheader(self, *_args, **_kwargs) -> None:
        return None

    def header(self, *_args, **_kwargs) -> None:
        return None

    def columns(self, count):
        return [_FakeContext() for _idx in range(count)]

    def metric(self, *_args, **_kwargs) -> None:
        return None

    def info(self, *_args, **_kwargs) -> None:
        return None

    def warning(self, *_args, **_kwargs) -> None:
        return None

    def error(self, *_args, **_kwargs) -> None:
        return None

    def success(self, *_args, **_kwargs) -> None:
        return None

    def dataframe(self, *_args, **_kwargs) -> None:
        return None

    def selectbox(self, _label, options, index=0):
        return options[index]

    class sidebar:  # noqa: N801 -- mirrors st.sidebar's attribute access
        @staticmethod
        def title(*_args, **_kwargs) -> None:
            return None

        @staticmethod
        def caption(*_args, **_kwargs) -> None:
            return None

        @staticmethod
        def radio(_label, options):
            return options[0]

        @staticmethod
        def selectbox(_label, options, index=0):
            return options[index]

        @staticmethod
        def divider() -> None:
            return None

        @staticmethod
        def button(*_args, **_kwargs) -> bool:
            return False


class _FakeRow:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def as_dict(self) -> dict[str, Any]:
        return dict(self._values)


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def collect(self) -> list[_FakeRow]:
        return [_FakeRow(row) for row in self._rows]


class _FakeSession:
    """Returns canned rows keyed by a substring of the issued SQL."""

    def __init__(self, table_rows: dict[str, list[dict[str, Any]]]) -> None:
        self._table_rows = table_rows

    def sql(self, sql: str):
        for needle, rows in self._table_rows.items():
            if needle in sql:
                return _FakeResult(rows)
        return _FakeResult([])


class _RaisingSession:
    def sql(self, sql: str):
        raise RuntimeError("simulated Snowflake failure: not authorized")


def _load_app(session_factory):
    spec = importlib.util.spec_from_file_location(
        "_mdm_dashboard_streamlit_app_under_test", STREAMLIT_APP
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {STREAMLIT_APP}")

    fake_snowflake = types.ModuleType("snowflake")
    fake_snowflake_snowpark = types.ModuleType("snowflake.snowpark")
    fake_snowflake_context = types.ModuleType("snowflake.snowpark.context")
    fake_snowflake_context.get_active_session = session_factory

    replacements = {
        "streamlit": _FakeStreamlit(),
        "snowflake": fake_snowflake,
        "snowflake.snowpark": fake_snowflake_snowpark,
        "snowflake.snowpark.context": fake_snowflake_context,
    }
    originals = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


_GENERATION_ROW = {
    "GENERATION_ID": "gen-1",
    "ACTIVATED_AT": "2026-07-25T11:13:39",
    "STATUS": "activated",
    "RULE_VERSION": "v1",
    "SCHEMA_VERSION": "v1",
    "NODE_COUNT": 193063,
    "EDGE_COUNT": 157732,
    "CREATED_AT": "2026-07-25T11:09:39",
    "VERIFIED_AT": "2026-07-25T11:12:29",
}

_ENTITY_ROWS = [
    {
        "GENERATION_ID": "gen-1",
        "ENTITY_TYPE": "person",
        "MDM_ACTIVE_COUNT": 6053,
        "GRAPH_NODE_COUNT": 5892,
        "MDM_MINUS_GRAPH": 161,
        "GRAPH_MINUS_MDM": 0,
        "STATUS": "Mismatch",
    },
    {
        "GENERATION_ID": "gen-1",
        "ENTITY_TYPE": "fund",
        "MDM_ACTIVE_COUNT": 129992,
        "GRAPH_NODE_COUNT": 129992,
        "MDM_MINUS_GRAPH": 0,
        "GRAPH_MINUS_MDM": 0,
        "STATUS": "OK",
    },
]

_RELATIONSHIP_ROWS = [
    {
        "GENERATION_ID": "gen-1",
        "RELATIONSHIP_TYPE": "HOLDS",
        "MDM_ACTIVE_COUNT": 5253,
        "GRAPH_EDGE_COUNT": 0,
        "MDM_MINUS_GRAPH": 5253,
        "GRAPH_MINUS_MDM": 0,
        "STATUS": "Mismatch",
    },
]

_MISMATCH_ROWS = [
    {
        "GENERATION_ID": "gen-1",
        "SAMPLE_TYPE": "missing_graph_nodes",
        "ENTITY_TYPE": "person",
        "RELATIONSHIP_TYPE": None,
        "NODE_ID": "node-1",
        "EDGE_ID": None,
        "SOURCE_NODE_ID": None,
        "TARGET_NODE_ID": None,
    },
    {
        "GENERATION_ID": "gen-1",
        "SAMPLE_TYPE": "missing_graph_edge_endpoints",
        "ENTITY_TYPE": None,
        "RELATIONSHIP_TYPE": "COMPANY_HOLDS",
        "NODE_ID": None,
        "EDGE_ID": "edge-1",
        "SOURCE_NODE_ID": "src-1",
        "TARGET_NODE_ID": "tgt-1",
    },
]

_NATIVE_APP_ROWS = [
    {
        "GENERATION_ID": "gen-1",
        "CHECK_NAME": "graph_info",
        "STATUS": "ok",
        "DETAIL": "1 row(s) returned.",
        "REMEDIATION": "",
    },
    {
        "GENERATION_ID": "gen-1",
        "CHECK_NAME": "list_graphs",
        "STATUS": "failed",
        "DETAIL": "Check failed before returning rows.",
        "REMEDIATION": "Capture the app version and exact error as an external blocker.",
    },
]


def _happy_path_session() -> _FakeSession:
    return _FakeSession(
        {
            "V_GRAPH_REVIEW_ACTIVE_GENERATION": [_GENERATION_ROW],
            "V_GRAPH_REVIEW_ENTITY_PARITY": _ENTITY_ROWS,
            "V_GRAPH_REVIEW_RELATIONSHIP_PARITY": _RELATIONSHIP_ROWS,
            "V_GRAPH_REVIEW_MISMATCH_SAMPLE": _MISMATCH_ROWS,
            "V_GRAPH_REVIEW_NATIVE_APP_CHECK": _NATIVE_APP_ROWS,
        }
    )


class ReadGraphReviewMetricsTests(unittest.TestCase):
    def test_happy_path_maps_view_rows_into_expected_shape(self) -> None:
        module = _load_app(_happy_path_session)

        metrics = module._read_graph_review_metrics()

        self.assertTrue(metrics["available"])
        self.assertEqual(metrics["state"], "ok")
        self.assertEqual(metrics["snowflake_graph_nodes"], 193063)
        self.assertEqual(metrics["snowflake_graph_edges"], 157732)
        self.assertEqual(metrics["target"]["generation_id"], "gen-1")

        entity_row = next(
            row for row in metrics["entity_comparison"] if row["entity_type"] == "person"
        )
        self.assertEqual(entity_row["mdm_active_count"], 6053)
        self.assertEqual(entity_row["snowflake_graph_node_count"], 5892)
        self.assertEqual(entity_row["mdm_minus_graph"], 161)
        self.assertEqual(entity_row["status"], "Mismatch")

        relationship_row = metrics["relationship_comparison"][0]
        self.assertEqual(relationship_row["relationship_type"], "HOLDS")
        self.assertEqual(relationship_row["snowflake_graph_edge_count"], 0)

        self.assertEqual(len(metrics["diagnostics"]["missing_graph_nodes"]), 1)
        self.assertEqual(metrics["diagnostics"]["missing_graph_nodes"][0]["node_id"], "node-1")
        endpoint_row = metrics["diagnostics"]["missing_graph_edge_endpoints"][0]
        self.assertEqual(endpoint_row["source_node_id"], "src-1")
        self.assertEqual(endpoint_row["target_node_id"], "tgt-1")

        self.assertEqual(metrics["native_app"]["status"], "failed")
        self.assertEqual(len(metrics["native_app"]["failing_checks"]), 1)
        self.assertEqual(metrics["native_app"]["failing_checks"][0]["check"], "list_graphs")

    def test_no_active_generation_returns_unavailable_with_distinct_state(self) -> None:
        module = _load_app(lambda: _FakeSession({}))

        metrics = module._read_graph_review_metrics()

        self.assertFalse(metrics["available"])
        self.assertEqual(metrics["state"], "no_active_generation")
        self.assertIn("No generation has ever been activated", metrics["message"])

    def test_query_failure_returns_unavailable_not_a_crash(self) -> None:
        module = _load_app(_RaisingSession)

        metrics = module._read_graph_review_metrics()

        self.assertFalse(metrics["available"])
        self.assertEqual(metrics["state"], "unavailable")
        self.assertIn("simulated Snowflake failure", metrics["message"])

    def test_all_native_app_checks_ok_yields_ok_status_and_no_failures(self) -> None:
        session = _FakeSession(
            {
                "V_GRAPH_REVIEW_ACTIVE_GENERATION": [_GENERATION_ROW],
                "V_GRAPH_REVIEW_ENTITY_PARITY": [],
                "V_GRAPH_REVIEW_RELATIONSHIP_PARITY": [],
                "V_GRAPH_REVIEW_MISMATCH_SAMPLE": [],
                "V_GRAPH_REVIEW_NATIVE_APP_CHECK": [
                    {
                        "GENERATION_ID": "gen-1",
                        "CHECK_NAME": "bfs",
                        "STATUS": "ok",
                        "DETAIL": "1 row(s) returned.",
                        "REMEDIATION": "",
                    }
                ],
            }
        )
        module = _load_app(lambda: session)

        metrics = module._read_graph_review_metrics()

        self.assertEqual(metrics["native_app"]["status"], "ok")
        self.assertEqual(metrics["native_app"]["failing_checks"], [])


class HelperFunctionTests(unittest.TestCase):
    def test_has_graph_mismatches_true_when_any_parity_row_mismatches(self) -> None:
        module = _load_app(_happy_path_session)
        metrics = module._read_graph_review_metrics()

        self.assertTrue(module._has_graph_mismatches(metrics))

    def test_has_graph_mismatches_false_when_everything_matches(self) -> None:
        module = _load_app(_happy_path_session)
        metrics = {
            "entity_comparison": [
                {"mdm_active_count": 1, "snowflake_graph_node_count": 1, "mdm_minus_graph": 0, "graph_minus_mdm": 0}
            ],
            "relationship_comparison": [],
            "diagnostics": module._empty_diagnostics(),
        }

        self.assertFalse(module._has_graph_mismatches(metrics))

    def test_entity_filter_options_includes_types_from_comparison_and_diagnostics(self) -> None:
        module = _load_app(_happy_path_session)
        metrics = module._read_graph_review_metrics()

        options = module._entity_filter_options(metrics)

        self.assertEqual(options[0], module.FILTER_ALL)
        self.assertIn("person", options)
        self.assertIn("fund", options)

    def test_relationship_filter_options_includes_types_from_endpoint_diagnostics(self) -> None:
        module = _load_app(_happy_path_session)
        metrics = module._read_graph_review_metrics()

        options = module._relationship_filter_options(metrics)

        self.assertIn("HOLDS", options)
        self.assertIn("COMPANY_HOLDS", options)

    def test_int_value_defaults_none_and_invalid_to_zero(self) -> None:
        module = _load_app(_happy_path_session)

        self.assertEqual(module._int_value(None), 0)
        self.assertEqual(module._int_value("not a number"), 0)
        self.assertEqual(module._int_value(42), 42)


class RenderSmokeTests(unittest.TestCase):
    """Render functions must not crash for either an available or an
    unavailable metrics payload -- streamlit itself is faked out, so these
    only prove control flow, not visual output."""

    def test_render_overview_handles_unavailable_metrics(self) -> None:
        module = _load_app(lambda: _FakeSession({}))
        metrics = module._read_graph_review_metrics()

        module.render_overview(metrics)  # must not raise

    def test_render_overview_handles_available_metrics(self) -> None:
        module = _load_app(_happy_path_session)
        metrics = module._read_graph_review_metrics()

        module.render_overview(metrics)  # must not raise

    def test_render_parity_handles_available_metrics(self) -> None:
        module = _load_app(_happy_path_session)
        metrics = module._read_graph_review_metrics()

        module.render_parity(metrics, row_limit=50)  # must not raise

    def test_render_mismatch_diagnostics_handles_available_metrics(self) -> None:
        module = _load_app(_happy_path_session)
        metrics = module._read_graph_review_metrics()

        module.render_mismatch_diagnostics(metrics, row_limit=50)  # must not raise


if __name__ == "__main__":
    unittest.main()
