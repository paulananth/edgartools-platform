"""Unit tests for ERDP-02 guidance facts Explore product."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

import pandas as pd

from edgar_warehouse.explore.guidance_facts import (
    GuidanceProbeError,
    GuidanceRowError,
    build_guidance_facts_table,
    current_guidance_rows,
    extract_guidance_from_earnings_release,
    extract_guidance_from_table,
    guidance_fact_key,
    load_firm_manual_csv,
    load_firm_manual_records,
    map_metric,
    normalize_guidance_row,
    parse_value_cell,
    validate_guidance_rows,
)


class MapMetricTests(unittest.TestCase):
    def test_revenue_variants(self) -> None:
        for label in ("Revenue", "Total revenue", "Net sales", "Net Revenue"):
            self.assertEqual(map_metric(label), ("revenue", False))

    def test_eps_diluted_variants(self) -> None:
        self.assertEqual(map_metric("Diluted EPS"), ("eps_diluted", False))
        self.assertEqual(map_metric("Diluted Earnings Per Share"), ("eps_diluted", False))

    def test_eps_basic_variants(self) -> None:
        self.assertEqual(map_metric("Basic EPS"), ("eps_basic", False))

    def test_non_gaap_marker_detected(self) -> None:
        metric, is_non_gaap = map_metric("Adjusted EBITDA")
        self.assertEqual(metric, "ebitda")
        self.assertTrue(is_non_gaap)

    def test_non_gaap_eps(self) -> None:
        metric, is_non_gaap = map_metric("Non-GAAP Diluted EPS")
        self.assertEqual(metric, "eps_diluted")
        self.assertTrue(is_non_gaap)

    def test_ebitda_before_ebit_substring_match(self) -> None:
        # "ebit" is a substring of "ebitda" -- pattern order must not misclassify.
        self.assertEqual(map_metric("EBITDA")[0], "ebitda")
        self.assertEqual(map_metric("EBIT margin")[0], "ebit")

    def test_unrecognized_label_is_other(self) -> None:
        self.assertEqual(map_metric("Some Unrelated Metric"), ("other", False))

    def test_none_label(self) -> None:
        self.assertEqual(map_metric(None), ("other", False))


class ParseValueCellTests(unittest.TestCase):
    def test_dollar_range(self) -> None:
        low, mid, high = parse_value_cell("$1.20 - $1.25")
        self.assertAlmostEqual(low, 1.20)
        self.assertAlmostEqual(mid, 1.225)
        self.assertAlmostEqual(high, 1.25)

    def test_word_to_range_with_commas(self) -> None:
        low, mid, high = parse_value_cell("1,200 to 1,300")
        self.assertEqual((low, mid, high), (1200.0, 1250.0, 1300.0))

    def test_point_value(self) -> None:
        self.assertEqual(parse_value_cell("42.5"), (42.5, 42.5, 42.5))

    def test_numeric_input(self) -> None:
        self.assertEqual(parse_value_cell(7), (7.0, 7.0, 7.0))

    def test_tuple_low_high(self) -> None:
        self.assertEqual(parse_value_cell((1.0, 2.0)), (1.0, 1.5, 2.0))

    def test_not_meaningful_returns_none(self) -> None:
        self.assertEqual(parse_value_cell("Not meaningful"), (None, None, None))

    def test_na_variants_return_none(self) -> None:
        for v in ("N/A", "NA", "-", "--", "", None):
            self.assertEqual(parse_value_cell(v), (None, None, None))

    def test_reversed_range_is_normalized(self) -> None:
        # If low/high are given backwards, still normalize to low <= high.
        low, mid, high = parse_value_cell("$1.30 - $1.20")
        self.assertEqual((low, high), (1.20, 1.30))


class NormalizeGuidanceRowTests(unittest.TestCase):
    def _base_row(self, **overrides):
        row = {
            "cik": "0000320193",
            "metric": "revenue",
            "fiscal_year": 2026,
            "fiscal_quarter": 3,
            "value_low": 1200.0,
            "value_high": 1300.0,
            "as_of": "2026-07-20",
            "source_system": "sec_8k",
            "accession_number": "0000320193-26-000042",
        }
        row.update(overrides)
        return row

    def test_minimal_valid_row(self) -> None:
        row = normalize_guidance_row(self._base_row())
        self.assertEqual(row["cik"], 320193)
        self.assertEqual(row["metric"], "revenue")
        self.assertEqual(row["period_type"], "quarterly")
        self.assertEqual(row["value_low"], 1200.0)
        self.assertEqual(row["value_high"], 1300.0)
        # D3: midpoint auto-fill is an optional read-side view, not
        # write-time required -- value_mid stays None when not supplied.
        self.assertIsNone(row["value_mid"])
        self.assertIsNotNone(row["fact_key"])
        self.assertFalse(row["is_non_gaap"])
        self.assertEqual(row["confidence"], "medium")

    def test_annual_period_type_defaults_from_quarter_zero(self) -> None:
        row = normalize_guidance_row(self._base_row(fiscal_quarter=0))
        self.assertEqual(row["period_type"], "annual")

    def test_missing_cik_rejected(self) -> None:
        row = self._base_row()
        del row["cik"]
        with self.assertRaises(GuidanceRowError):
            normalize_guidance_row(row)

    def test_missing_as_of_rejected(self) -> None:
        row = self._base_row()
        del row["as_of"]
        with self.assertRaises(GuidanceRowError):
            normalize_guidance_row(row)

    def test_no_values_rejected(self) -> None:
        row = self._base_row(value_low=None, value_high=None)
        with self.assertRaises(GuidanceRowError):
            normalize_guidance_row(row)

    def test_low_greater_than_high_rejected(self) -> None:
        row = self._base_row(value_low=1300.0, value_high=1200.0)
        with self.assertRaises(GuidanceRowError):
            normalize_guidance_row(row)

    def test_mid_outside_low_high_rejected(self) -> None:
        row = self._base_row(value_low=1200.0, value_high=1300.0, value_mid=5000.0)
        with self.assertRaises(GuidanceRowError):
            normalize_guidance_row(row)

    def test_sec_source_without_accession_rejected(self) -> None:
        row = self._base_row(accession_number=None)
        with self.assertRaises(GuidanceRowError):
            normalize_guidance_row(row)

    def test_firm_manual_without_accession_allowed(self) -> None:
        row = self._base_row(source_system="firm_manual", accession_number=None)
        normalized = normalize_guidance_row(row)
        self.assertIsNone(normalized["accession_number"])

    def test_invalid_fiscal_quarter_rejected(self) -> None:
        row = self._base_row(fiscal_quarter=5)
        with self.assertRaises(GuidanceRowError):
            normalize_guidance_row(row)

    def test_unknown_source_system_falls_back_to_other(self) -> None:
        row = self._base_row(source_system="bloomberg", accession_number=None)
        normalized = normalize_guidance_row(row)
        self.assertEqual(normalized["source_system"], "other")

    def test_unknown_metric_falls_back_to_other(self) -> None:
        row = self._base_row(metric="widgets_shipped")
        normalized = normalize_guidance_row(row)
        self.assertEqual(normalized["metric"], "other")

    def test_excerpt_truncated_to_500_chars(self) -> None:
        row = self._base_row(excerpt="x" * 900)
        normalized = normalize_guidance_row(row)
        self.assertEqual(len(normalized["excerpt"]), 500)


class ValidateGuidanceRowsTests(unittest.TestCase):
    def test_splits_accepted_and_rejected(self) -> None:
        rows = [
            {
                "cik": 1, "metric": "revenue", "fiscal_year": 2026, "fiscal_quarter": 1,
                "value_low": 100.0, "value_high": 200.0, "as_of": "2026-01-01",
                "source_system": "sec_8k", "accession_number": "0000000001-26-000001",
            },
            {
                # Missing value columns -> reject (A02.5 constraint)
                "cik": 1, "metric": "revenue", "fiscal_year": 2026, "fiscal_quarter": 1,
                "as_of": "2026-01-01", "source_system": "sec_8k",
                "accession_number": "0000000001-26-000001",
            },
        ]
        accepted, rejected = validate_guidance_rows(rows)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(rejected), 1)
        self.assertIn("reject_reason", rejected[0])


class FactKeyTests(unittest.TestCase):
    def test_deterministic(self) -> None:
        args = (320193, "revenue", 2026, 3, date(2026, 7, 20), "acc-1", False, "sec_8k")
        self.assertEqual(guidance_fact_key(*args), guidance_fact_key(*args))

    def test_distinct_source_system_yields_distinct_key(self) -> None:
        a = guidance_fact_key(320193, "revenue", 2026, 3, date(2026, 7, 20), "acc-1", False, "sec_8k")
        b = guidance_fact_key(320193, "revenue", 2026, 3, date(2026, 7, 20), "acc-1", False, "firm_manual")
        self.assertNotEqual(a, b)


class BuildGuidanceFactsTableTests(unittest.TestCase):
    def test_empty_rows_returns_typed_empty_table(self) -> None:
        table = build_guidance_facts_table([])
        self.assertEqual(table.num_rows, 0)
        self.assertIn("metric", table.schema.names)

    def test_rows_cast_to_schema(self) -> None:
        rows = [{
            "cik": 320193, "metric": "revenue", "fiscal_year": 2026, "fiscal_quarter": 3,
            "value_low": 100.0, "value_high": 200.0, "as_of": "2026-07-20",
            "source_system": "sec_8k", "accession_number": "0000320193-26-000042",
        }]
        table = build_guidance_facts_table(rows)
        self.assertEqual(table.num_rows, 1)
        self.assertEqual(table.column("metric").to_pylist(), ["revenue"])


class CurrentGuidanceRowsTests(unittest.TestCase):
    def test_latest_as_of_wins_per_base_key(self) -> None:
        base = {
            "cik": 320193, "metric": "revenue", "fiscal_year": 2026, "fiscal_quarter": 3,
            "source_system": "sec_8k", "accession_number": "0000320193-26-000042",
        }
        rows = [
            {**base, "value_low": 100.0, "value_high": 200.0, "as_of": "2026-07-01"},
            {**base, "value_low": 150.0, "value_high": 250.0, "as_of": "2026-07-20"},
        ]
        current = current_guidance_rows(rows)
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["as_of"], date(2026, 7, 20))
        self.assertEqual(current[0]["value_low"], 150.0)


class FirmManualLoaderTests(unittest.TestCase):
    def test_load_records_defaults_source_system(self) -> None:
        rows = load_firm_manual_records([
            {
                "cik": "1234", "metric": "revenue", "fiscal_year": 2026,
                "fiscal_quarter": 2, "value_low": 500.0, "value_high": 600.0,
            }
        ], default_as_of=date(2026, 7, 1))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_system"], "firm_manual")
        self.assertEqual(rows[0]["as_of"], date(2026, 7, 1))
        self.assertEqual(rows[0]["confidence"], "high")
        self.assertIsNone(rows[0]["accession_number"])

    def test_load_csv_round_trip(self) -> None:
        # A02.7: firm_manual load path works for >=1 test CIK without SEC parse.
        csv_text = (
            "cik,metric,fiscal_year,fiscal_quarter,value_low,value_high\n"
            "1234,revenue,2026,2,500,600\n"
            "1234,eps_diluted,2026,2,1.10,1.20\n"
        )
        rows = load_firm_manual_csv(csv_text, default_as_of=date(2026, 7, 1))
        self.assertEqual(len(rows), 2)
        metrics = {r["metric"] for r in rows}
        self.assertEqual(metrics, {"revenue", "eps_diluted"})
        for r in rows:
            self.assertEqual(r["source_system"], "firm_manual")


class _FakeFinancialTable:
    """Duck-typed FinancialTable stand-in (real one has scaled_dataframe/dataframe)."""

    def __init__(self, dataframe: pd.DataFrame) -> None:
        self.dataframe = dataframe
        self.scaled_dataframe = dataframe


class _FakeEarningsRelease:
    def __init__(self, guidance_table) -> None:
        self._guidance_table = guidance_table

    @property
    def guidance(self):
        return self._guidance_table


class ExtractGuidanceFromTableTests(unittest.TestCase):
    """A02.1: curated sample of accessions with numeric guidance.

    Each fixture below represents a structurally distinct real-world
    guidance-table shape (range cell, point value, non-GAAP label, mixed
    metrics, unrecognized row) rather than a live SEC fetch -- consistent
    with this module's synthetic-fixture testing style (mirrors
    test_earnings_calendar.py, which tests normalization against hand-built
    dicts, not live vendor payloads).
    """

    def _extract(self, df: pd.DataFrame, accession: str, **kwargs):
        defaults = dict(
            cik=320193, accession_number=accession, filing_date="2026-07-20",
            fiscal_year=2026, fiscal_quarter=3, parser_version="guidance_v1",
        )
        defaults.update(kwargs)
        return extract_guidance_from_table(dataframe=df, **defaults)

    def test_accession_1_range_cell(self) -> None:
        df = pd.DataFrame({"Q3 2026": ["$1,200 - $1,300"]}, index=["Revenue"])
        rows = self._extract(df, "0000320193-26-000001")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["accession_number"], "0000320193-26-000001")
        self.assertTrue(any(v is not None for v in
                             (rows[0]["value_low"], rows[0]["value_mid"], rows[0]["value_high"])))

    def test_accession_2_point_value(self) -> None:
        df = pd.DataFrame({"Q3 2026": [1.22]}, index=["Diluted EPS"])
        rows = self._extract(df, "0000320193-26-000002")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["metric"], "eps_diluted")
        self.assertEqual(rows[0]["value_low"], rows[0]["value_high"])

    def test_accession_3_non_gaap_label(self) -> None:
        df = pd.DataFrame({"FY2026": ["$500 - $520"]}, index=["Adjusted EBITDA"])
        rows = self._extract(df, "0000320193-26-000003", fiscal_quarter=0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["metric"], "ebitda")
        self.assertTrue(rows[0]["is_non_gaap"])

    def test_accession_4_multi_metric(self) -> None:
        df = pd.DataFrame(
            {"Q3 2026": ["$1,200 - $1,300", "$1.20 - $1.25"]},
            index=["Total revenue", "Diluted EPS"],
        )
        rows = self._extract(df, "0000320193-26-000004")
        self.assertEqual(len(rows), 2)
        metrics = {r["metric"] for r in rows}
        self.assertEqual(metrics, {"revenue", "eps_diluted"})

    def test_accession_5_unrecognized_row_excluded(self) -> None:
        df = pd.DataFrame(
            {"Q3 2026": ["$1,200 - $1,300", "Some proprietary index"]},
            index=["Revenue", "Widget Happiness Score"],
        )
        rows = self._extract(df, "0000320193-26-000005")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["metric"], "revenue")

    def test_all_five_accessions_produce_valid_gold_rows(self) -> None:
        # A02.1: all 5 fixtures above pass full validation with accession set.
        cases = [
            (pd.DataFrame({"Q3 2026": ["$1,200 - $1,300"]}, index=["Revenue"]),
             "0000320193-26-000001"),
            (pd.DataFrame({"Q3 2026": [1.22]}, index=["Diluted EPS"]),
             "0000320193-26-000002"),
            (pd.DataFrame({"FY2026": ["$500 - $520"]}, index=["Adjusted EBITDA"]),
             "0000320193-26-000003"),
            (pd.DataFrame({"Q3 2026": ["$1,200 - $1,300", "$1.20 - $1.25"]},
                          index=["Total revenue", "Diluted EPS"]),
             "0000320193-26-000004"),
            (pd.DataFrame({"Q3 2026": ["$1,200 - $1,300", "Some index"]},
                          index=["Revenue", "Widget Happiness Score"]),
             "0000320193-26-000005"),
        ]
        for df, accession in cases:
            candidates = self._extract(df, accession)
            accepted, rejected = validate_guidance_rows(candidates)
            self.assertGreaterEqual(len(accepted), 1, f"no accepted rows for {accession}")
            for row in accepted:
                self.assertEqual(row["accession_number"], accession)
                self.assertIn(row["source_system"], {"sec_8k", "sec_10q", "sec_10k"})
                self.assertTrue(
                    any(v is not None for v in
                        (row["value_low"], row["value_mid"], row["value_high"]))
                )

    def test_no_numeric_value_yields_no_row(self) -> None:
        df = pd.DataFrame({"Q3 2026": ["Not meaningful"]}, index=["Revenue"])
        rows = self._extract(df, "0000320193-26-000006")
        self.assertEqual(rows, [])

    def test_empty_dataframe(self) -> None:
        rows = self._extract(pd.DataFrame(), "0000320193-26-000007")
        self.assertEqual(rows, [])


class ExtractGuidanceFromEarningsReleaseTests(unittest.TestCase):
    def test_extracts_from_duck_typed_earnings_release(self) -> None:
        df = pd.DataFrame({"Q3 2026": ["$1,200 - $1,300"]}, index=["Revenue"])
        er = _FakeEarningsRelease(_FakeFinancialTable(df))
        rows = extract_guidance_from_earnings_release(
            er, cik=320193, accession_number="0000320193-26-000042",
            filing_date="2026-07-20", fiscal_year=2026, fiscal_quarter=3,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["accession_number"], "0000320193-26-000042")

    def test_no_guidance_table_yields_empty_list(self) -> None:
        er = _FakeEarningsRelease(None)
        rows = extract_guidance_from_earnings_release(
            er, cik=320193, accession_number="0000320193-26-000042",
            filing_date="2026-07-20",
        )
        self.assertEqual(rows, [])

    def test_guidance_property_raising_is_not_absorbed(self) -> None:
        # Regression guard: a genuine exception while probing for guidance
        # must be distinguishable from a confirmed "no guidance" (empty
        # list) -- silently absorbing both the same way is exactly the bug
        # fixed in the GUIDANCE_FACTS promotion-checklist blocking
        # prerequisite (ticket 04, erdp-coverage-promotion).
        class _RaisingEarningsRelease:
            @property
            def guidance(self):
                raise RuntimeError("boom")

        with self.assertRaises(GuidanceProbeError):
            extract_guidance_from_earnings_release(
                _RaisingEarningsRelease(), cik=1, accession_number="acc-1", filing_date="2026-01-01",
            )

    def test_dataframe_access_raising_is_not_absorbed(self) -> None:
        class _RaisingTable:
            @property
            def scaled_dataframe(self):
                raise RuntimeError("scaled boom")

            @property
            def dataframe(self):
                raise RuntimeError("plain boom")

        er = _FakeEarningsRelease(_RaisingTable())
        with self.assertRaises(GuidanceProbeError):
            extract_guidance_from_earnings_release(
                er, cik=1, accession_number="acc-1", filing_date="2026-01-01",
            )

    def test_empty_dataframe_is_a_confirmed_absence_not_an_error(self) -> None:
        df = pd.DataFrame()
        er = _FakeEarningsRelease(_FakeFinancialTable(df))
        rows = extract_guidance_from_earnings_release(
            er, cik=1, accession_number="acc-1", filing_date="2026-01-01",
        )
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
