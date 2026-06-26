from __future__ import annotations

import importlib.util
import math
import sys
import types
import unittest
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


def _load_app():
    spec = importlib.util.spec_from_file_location(
        "_snowflake_streamlit_app_under_test",
        STREAMLIT_APP,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load streamlit_app.py")

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


if __name__ == "__main__":
    unittest.main()
