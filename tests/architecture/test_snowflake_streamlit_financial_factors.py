from __future__ import annotations

import builtins
import importlib.util
import math
import re
import shutil
import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
STREAMLIT_APP = REPO_ROOT / "infra" / "snowflake" / "streamlit" / "streamlit_app.py"


class _FakeCacheResource:
    def __call__(self, func=None, *args, **kwargs):
        if func is None:
            return lambda wrapped: wrapped
        return func


class _FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return False

    def metric(self, *_args, **_kwargs) -> None:
        return None

    def subheader(self, *_args, **_kwargs) -> None:
        return None


class _FakeStreamlit:
    cache_resource = _FakeCacheResource()

    def set_page_config(self, *_args, **_kwargs) -> None:
        return None

    def tabs(self, labels):
        return [_FakeContext() for _label in labels]

    def columns(self, count):
        return [_FakeContext() for _idx in range(count)]

    def expander(self, *_args, **_kwargs):
        return _FakeContext()

    def header(self, *_args, **_kwargs) -> None:
        return None

    def subheader(self, *_args, **_kwargs) -> None:
        return None

    def divider(self) -> None:
        return None

    def metric(self, *_args, **_kwargs) -> None:
        return None

    def info(self, *_args, **_kwargs) -> None:
        return None

    def warning(self, *_args, **_kwargs) -> None:
        return None

    def error(self, *_args, **_kwargs) -> None:
        return None

    def caption(self, *_args, **_kwargs) -> None:
        return None

    def write(self, *_args, **_kwargs) -> None:
        return None

    def dataframe(self, *_args, **_kwargs) -> None:
        return None

    def plotly_chart(self, *_args, **_kwargs) -> None:
        return None

    def text_input(self, *_args, **_kwargs) -> str:
        return ""

    def selectbox(self, _label, options):
        return options[0]


class _FakeQuery:
    def __init__(self, sql: str, params=None) -> None:
        self.sql = sql
        self.params = params

    def to_pandas(self):
        if "company_count" in self.sql:
            return pd.DataFrame(
                [
                    {
                        "COMPANY_COUNT": 1,
                        "FILING_COUNT": 2,
                        "LAST_FILING_DATE": None,
                    }
                ]
            )
        return pd.DataFrame()


class _FakeSession:
    def sql(self, sql: str, params=None):
        return _FakeQuery(sql, params=params)


class _RecordingFakeSession:
    """Records every SQL string issued through it -- GH-246 criterion 3."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def sql(self, sql: str, params=None):
        self.queries.append(sql)
        return _FakeQuery(sql, params=params)


def _load_app(app_path: Path = STREAMLIT_APP, *, block_edgar_warehouse: bool = False):
    """Load ``streamlit_app.py`` (or a copy) with streamlit/plotly/snowflake faked out.

    ``block_edgar_warehouse`` simulates the real Streamlit-in-Snowflake
    runtime, which has no ``edgar_warehouse`` package installed (see
    deploy.sh) -- it forces the module's mode-contract import to fall
    through to its flat ``dashboard_modes`` fallback branch, the one code
    path this test file otherwise never exercises.
    """
    spec = importlib.util.spec_from_file_location(
        "_snowflake_streamlit_app_under_test",
        app_path,
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {app_path}")

    fake_plotly_express = types.ModuleType("plotly.express")
    fake_plotly_express.bar = lambda *_args, **_kwargs: None
    fake_plotly_express.line = lambda *_args, **_kwargs: None
    fake_plotly_express.area = lambda *_args, **_kwargs: None

    fake_plotly = types.ModuleType("plotly")
    fake_plotly.express = fake_plotly_express

    fake_snowflake = types.ModuleType("snowflake")
    fake_snowflake_snowpark = types.ModuleType("snowflake.snowpark")
    fake_snowflake_context = types.ModuleType("snowflake.snowpark.context")
    fake_snowflake_context.get_active_session = lambda: _FakeSession()

    replacements = {
        "streamlit": _FakeStreamlit(),
        "plotly": fake_plotly,
        "plotly.express": fake_plotly_express,
        "snowflake": fake_snowflake,
        "snowflake.snowpark": fake_snowflake_snowpark,
        "snowflake.snowpark.context": fake_snowflake_context,
    }
    originals = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)

    # The fallback branch does `from dashboard_modes import ...` as a bare
    # top-level module. Python caches modules by name in sys.modules, so a
    # prior test's flat dashboard_modes (from a different temp dir) would
    # otherwise be silently reused instead of resolving fresh via sys.path.
    dashboard_modes_original = sys.modules.pop("dashboard_modes", None)

    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if block_edgar_warehouse and (
            name == "edgar_warehouse" or name.startswith("edgar_warehouse.")
        ):
            raise ImportError(f"simulated SiS runtime: {name!r} is not installed")
        return real_import(name, *args, **kwargs)

    sys_path_before = list(sys.path)
    try:
        with unittest.mock.patch("builtins.__import__", side_effect=_blocking_import):
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = sys_path_before
        sys.modules.pop("dashboard_modes", None)
        if dashboard_modes_original is not None:
            sys.modules["dashboard_modes"] = dashboard_modes_original
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class SnowflakeStreamlitFinancialFactorsTests(unittest.TestCase):
    def test_metric_text_formats_missing_and_numeric_values(self) -> None:
        module = _load_app()

        self.assertEqual(module._metric_text(None, ".2f"), "—")
        self.assertEqual(module._metric_text(math.nan, ".2f"), "—")
        self.assertEqual(module._metric_text(12.345, ".2f"), "12.35")

    def test_financial_factors_query_uses_bound_cik_parameter(self) -> None:
        module = _load_app()
        calls = []

        def fake_safe_df(label, sql, params=None):
            calls.append({"label": label, "sql": sql, "params": params})
            return "sentinel"

        module._safe_df = fake_safe_df

        result = module._company_financial_factors("320193", limit="5")

        self.assertEqual(result, "sentinel")
        self.assertEqual(calls[0]["label"], "Financial factors")
        self.assertEqual(calls[0]["params"], [320193])
        self.assertIn("from EDGARTOOLS_GOLD.FINANCIAL_FACTORS", calls[0]["sql"])
        self.assertIn("where cik = ?", calls[0]["sql"])
        self.assertIn("limit 5", calls[0]["sql"])


class EquityResearchSectionTests(unittest.TestCase):
    """Company Details' ERDP-01..04 "Equity research (Explore)" section."""

    def test_consensus_estimates_query_uses_bound_cik_and_current_filter(self) -> None:
        module = _load_app()
        calls = []
        module._safe_df = lambda label, sql, params=None: calls.append(
            {"label": label, "sql": sql, "params": params}
        )

        module._company_consensus_estimates("320193", limit="5")

        self.assertEqual(calls[0]["label"], "Consensus estimates")
        self.assertEqual(calls[0]["params"], [320193])
        self.assertIn("from EDGARTOOLS_GOLD.CONSENSUS_ESTIMATES", calls[0]["sql"])
        self.assertIn("where cik = ? and is_current", calls[0]["sql"])
        self.assertIn("limit 5", calls[0]["sql"])

    def test_guidance_facts_query_uses_bound_cik_and_current_filter(self) -> None:
        module = _load_app()
        calls = []
        module._safe_df = lambda label, sql, params=None: calls.append(
            {"label": label, "sql": sql, "params": params}
        )

        module._company_guidance_facts(320193, limit=10)

        self.assertEqual(calls[0]["label"], "Guidance facts")
        self.assertEqual(calls[0]["params"], [320193])
        self.assertIn("from EDGARTOOLS_GOLD.GUIDANCE_FACTS", calls[0]["sql"])
        self.assertIn("where cik = ? and is_current", calls[0]["sql"])

    def test_earnings_calendar_query_uses_bound_cik_and_current_filter(self) -> None:
        module = _load_app()
        calls = []
        module._safe_df = lambda label, sql, params=None: calls.append(
            {"label": label, "sql": sql, "params": params}
        )

        module._company_earnings_calendar(320193)

        self.assertEqual(calls[0]["label"], "Earnings calendar")
        self.assertEqual(calls[0]["params"], [320193])
        self.assertIn("from EDGARTOOLS_GOLD.EARNINGS_CALENDAR", calls[0]["sql"])
        self.assertIn("where cik = ? and is_current", calls[0]["sql"])

    def test_transcript_events_query_uses_bound_cik_without_is_current(self) -> None:
        """Unlike the other 3 ERDP products, a transcript pointer is revalidated
        in place (MERGE on event_key), not versioned -- no is_current column."""
        module = _load_app()
        calls = []
        module._safe_df = lambda label, sql, params=None: calls.append(
            {"label": label, "sql": sql, "params": params}
        )

        module._company_transcript_events(320193)

        self.assertEqual(calls[0]["label"], "Transcript events")
        self.assertEqual(calls[0]["params"], [320193])
        self.assertIn("from EDGARTOOLS_GOLD.TRANSCRIPT_EVENTS", calls[0]["sql"])
        self.assertIn("where cik = ?", calls[0]["sql"])
        self.assertNotIn("is_current", calls[0]["sql"])

    def test_agent_view_blocks_equity_research_section(self) -> None:
        module = _load_app()
        called = []
        for name in (
            "_company_consensus_estimates",
            "_company_guidance_facts",
            "_company_earnings_calendar",
            "_company_transcript_events",
        ):
            setattr(module, name, lambda *_a, _n=name, **_k: called.append(_n))

        module._render_equity_research("agent_view", 320193)

        self.assertEqual(called, [])

    def test_explore_mode_renders_all_four_erdp_products(self) -> None:
        module = _load_app()
        called = []
        for name in (
            "_company_consensus_estimates",
            "_company_guidance_facts",
            "_company_earnings_calendar",
            "_company_transcript_events",
        ):
            setattr(
                module,
                name,
                lambda *_a, _n=name, **_k: (called.append(_n), pd.DataFrame())[1],
            )

        module._render_equity_research("explore", 320193)

        self.assertEqual(
            called,
            [
                "_company_consensus_estimates",
                "_company_guidance_facts",
                "_company_earnings_calendar",
                "_company_transcript_events",
            ],
        )


class AdvFundCountReconciliationTests(unittest.TestCase):
    """Ticket 04 (.scratch/adv-firm-roster-crosscheck/issues/
    04-reconciliation-model-dashboard.md): dashboard panel for the
    ADV_FUND_COUNT_RECONCILIATION gold model, added to render_pipeline()."""

    def test_mismatch_table_query_targets_correct_table_and_filters_mismatches(self) -> None:
        module = _load_app()
        calls = []
        module._safe_df = lambda label, sql, params=None: calls.append(
            {"label": label, "sql": sql, "params": params}
        )

        module._adv_fund_count_mismatches()

        self.assertEqual(calls[0]["label"], "ADV fund count reconciliation")
        self.assertIn(
            "from EDGARTOOLS_GOLD.ADV_FUND_COUNT_RECONCILIATION", calls[0]["sql"]
        )
        self.assertIn("where mismatch", calls[0]["sql"])
        self.assertIn("fund_count_delta", calls[0]["sql"])

    def test_summary_query_targets_correct_table_without_mismatch_filter(self) -> None:
        """The summary metric counts ALL firms (denominator), so its query
        must not filter to mismatched rows the way the detail table does."""
        module = _load_app()
        calls = []
        module._safe_df = lambda label, sql, params=None: calls.append(
            {"label": label, "sql": sql, "params": params}
        )

        module._adv_fund_count_reconciliation_summary()

        self.assertEqual(calls[0]["label"], "ADV fund count reconciliation summary")
        self.assertIn(
            "from EDGARTOOLS_GOLD.ADV_FUND_COUNT_RECONCILIATION", calls[0]["sql"]
        )
        self.assertNotIn("where mismatch", calls[0]["sql"])

    def test_mismatch_stats_defaults_to_zero_on_missing_or_empty_summary(self) -> None:
        module = _load_app()

        self.assertEqual(module._adv_reconciliation_mismatch_stats(None), (0, 0, 0.0))
        self.assertEqual(
            module._adv_reconciliation_mismatch_stats(pd.DataFrame()), (0, 0, 0.0)
        )

    def test_mismatch_stats_guards_against_division_by_zero(self) -> None:
        module = _load_app()

        summary = pd.DataFrame([{"TOTAL_FIRMS": 0, "MISMATCHED_FIRMS": 0}])

        self.assertEqual(module._adv_reconciliation_mismatch_stats(summary), (0, 0, 0.0))

    def test_mismatch_stats_computes_percentage(self) -> None:
        module = _load_app()

        summary = pd.DataFrame([{"TOTAL_FIRMS": 1000, "MISMATCHED_FIRMS": 250}])

        mismatched, total, pct = module._adv_reconciliation_mismatch_stats(summary)

        self.assertEqual(mismatched, 250)
        self.assertEqual(total, 1000)
        self.assertAlmostEqual(pct, 25.0)


class SingleAuthoritativePolicyTests(unittest.TestCase):
    """GH-246 criterion 2: one authoritative object-access policy, not
    duplicated allowlists -- proven by object identity, not equal values
    (equal values would still pass if someone re-introduced a hand copy)."""

    def test_constants_and_functions_are_the_same_objects_as_dashboard_modes(self) -> None:
        from edgar_warehouse.serving import dashboard_modes

        module = _load_app()

        self.assertIs(
            module.AGENT_VIEW_ALLOWED_OBJECTS, dashboard_modes.AGENT_VIEW_ALLOWED_OBJECTS
        )
        self.assertIs(module._is_object_allowed, dashboard_modes.is_object_allowed)
        self.assertIs(module._normalize_mode, dashboard_modes.normalize_mode)
        self.assertEqual(module.MODE_AGENT_VIEW, dashboard_modes.MODE_AGENT_VIEW)
        self.assertEqual(module.MODE_EXPLORE, dashboard_modes.MODE_EXPLORE)


class SisFallbackImportTests(unittest.TestCase):
    """GH-246: streamlit_app.py's flat-file import fallback for the real
    Streamlit-in-Snowflake runtime, which has no edgar_warehouse package
    installed (deploy.sh stages only the app, its policy/query modules, and
    environment.yml) -- otherwise-untested outside a live SiS deploy."""

    def test_falls_back_to_flat_dashboard_modes_when_package_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            shutil.copy(STREAMLIT_APP, tmp_path / "streamlit_app.py")
            shutil.copy(
                REPO_ROOT / "edgar_warehouse" / "serving" / "dashboard_modes.py",
                tmp_path / "dashboard_modes.py",
            )
            shutil.copy(
                REPO_ROOT
                / "edgar_warehouse"
                / "serving"
                / "dashboard_query_registry.py",
                tmp_path / "dashboard_query_registry.py",
            )
            shutil.copy(
                REPO_ROOT
                / "edgar_warehouse"
                / "serving"
                / "dashboard_workflows.py",
                tmp_path / "dashboard_workflows.py",
            )

            module = _load_app(tmp_path / "streamlit_app.py", block_edgar_warehouse=True)

        self.assertEqual(module.MODE_AGENT_VIEW, "agent_view")
        self.assertEqual(module.MODE_EXPLORE, "explore")
        self.assertTrue(module._is_object_allowed("explore", "ANYTHING"))
        self.assertFalse(module._is_object_allowed("agent_view", "COMPANY"))
        self.assertTrue(module._is_object_allowed("agent_view", "SUBJECT_FEATURE_SCREEN"))

    def test_missing_staged_dashboard_modes_fails_loudly(self) -> None:
        """If dashboard_modes.py isn't actually staged next to streamlit_app.py
        (a deploy.sh packaging regression), loading must raise -- not silently
        fall back to some other behavior that masks the missing file."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            shutil.copy(STREAMLIT_APP, tmp_path / "streamlit_app.py")
            # deliberately not staging dashboard_modes.py alongside it

            with self.assertRaises(ImportError):
                _load_app(tmp_path / "streamlit_app.py", block_edgar_warehouse=True)


class AgentViewQueryAllowlistTests(unittest.TestCase):
    """GH-246 criterion 3: record every query issued by Agent View routes,
    fail on any non-allowlisted object.

    Covers summary, company search, identity, and detail.  The contract query
    registry is the only Agent View SQL source.
    """

    def test_agent_view_summary_and_company_routes_stay_within_allowlist(self) -> None:
        module = _load_app()
        recorder = _RecordingFakeSession()
        module._session = lambda: recorder

        module.render_summary(mode="agent_view")
        module._lookup_contract_subjects("Apple")
        module._render_agent_view_company(320193)

        self.assertTrue(recorder.queries, "expected at least one query to be recorded")
        for sql in recorder.queries:
            referenced = re.findall(r"from\s+([A-Za-z0-9_.]+)", sql, flags=re.IGNORECASE)
            self.assertTrue(referenced, f"no FROM clause found in recorded query: {sql}")
            for ref in referenced:
                bare = ref.split(".")[-1].upper()
                self.assertIn(
                    bare,
                    module.AGENT_VIEW_ALLOWED_OBJECTS,
                    f"Agent View issued a query against a non-allowlisted "
                    f"object {bare!r}: {sql}",
                )

    def test_agent_view_registry_contains_every_route_query(self) -> None:
        module = _load_app()
        query_ids = {
            "agent.contract_status",
            "agent.subject_search",
            "agent.subject_bundle",
        }
        for query_id in query_ids:
            query = module.registered_query(query_id)
            self.assertLessEqual(query.max_rows, 25)
            self.assertTrue(
                module._is_object_allowed("agent_view", query.object_name),
                query_id,
            )

    def test_unregistered_agent_query_fails_closed(self) -> None:
        module = _load_app()
        with self.assertRaisesRegex(KeyError, "unregistered dashboard query"):
            module.registered_query("agent.free_gold")


class SecretSafeFailureCopyTests(unittest.TestCase):
    def test_connector_exception_is_not_rendered(self) -> None:
        module = _load_app()
        warnings = []
        module._df = lambda *_a, **_k: (_ for _ in ()).throw(
            RuntimeError("password=secret account=prod")
        )
        module.st.warning = warnings.append

        self.assertIsNone(module._safe_df("Company lookup", "select 1"))
        self.assertEqual(len(warnings), 1)
        self.assertNotIn("secret", warnings[0])
        self.assertNotIn("account=prod", warnings[0])
        self.assertIn("temporarily unavailable", warnings[0])


if __name__ == "__main__":
    unittest.main()
