"""Ticket 10 — Subject Feature Screen (issuer ranking)."""

from __future__ import annotations

import unittest

from edgar_warehouse.serving.decision_contract import DECISION_CONTRACT_VERSION
from edgar_warehouse.serving.subject_feature_screen import (
    COVERAGE_EMPTY,
    COVERAGE_NOT_APPLICABLE,
    COVERAGE_PRESENT,
    COVERAGE_UNAVAILABLE,
    FORBIDDEN_MARKET_FIELDS,
    PURE_SEC_FEATURE_KEYS,
    build_subject_feature_screen,
    decision_subject_universe,
    select_as_of_feature_periods,
)


def _wm(**overrides):
    base = {
        "business_date": "2024-06-30",
        "gold_run_id": "gold-1",
        "graph_generation_id": "gen-1",
        "silver_completeness_ok": True,
        "graph_parity_ok": True,
    }
    base.update(overrides)
    return base


def _period(cik, fiscal_period, period_end, fiscal_year=2023, **metrics):
    row = {
        "cik": cik,
        "fiscal_period": fiscal_period,
        "period_end": period_end,
        "fiscal_year": fiscal_year,
        "accession_number": f"acc-{cik}-{fiscal_period}-{period_end}",
        "form_type": "10-K" if fiscal_period == "FY" else "10-Q",
    }
    row.update(metrics)
    return row


class UniverseTests(unittest.TestCase):
    def test_intersection_of_warehouse_and_mdm_active(self) -> None:
        u = decision_subject_universe(
            warehouse_active_ciks=[1, 2, 3],
            mdm_active_ciks=[2, 3, 4],
        )
        self.assertEqual(u, (2, 3))

    def test_empty_when_either_side_empty(self) -> None:
        self.assertEqual(
            decision_subject_universe(warehouse_active_ciks=[1], mdm_active_ciks=[]),
            (),
        )


class AsOfFeatureSelectionTests(unittest.TestCase):
    def test_fy_selected_and_interim_only_when_newer(self) -> None:
        rows = [
            _period(1, "FY", "2023-12-31", fiscal_year=2023, revenue=100.0),
            _period(1, "Q1", "2023-03-31", fiscal_year=2023, revenue=20.0),  # older than FY end
            _period(1, "Q1", "2024-03-31", fiscal_year=2024, revenue=30.0),  # newer
        ]
        selected = select_as_of_feature_periods(rows)
        self.assertEqual(selected["fy"]["period_end"], "2023-12-31")
        self.assertEqual(selected["interim"]["period_end"], "2024-03-31")
        self.assertIsNone(selected.get("stale_interim"))

    def test_no_interim_when_none_newer_than_fy(self) -> None:
        rows = [
            _period(1, "FY", "2023-12-31", revenue=100.0),
            _period(1, "Q3", "2023-09-30", revenue=70.0),
        ]
        selected = select_as_of_feature_periods(rows)
        self.assertIsNotNone(selected["fy"])
        self.assertIsNone(selected["interim"])

    def test_null_not_coerced_to_zero(self) -> None:
        rows = [_period(1, "FY", "2023-12-31", revenue=None, net_income=5.0)]
        selected = select_as_of_feature_periods(rows)
        self.assertIsNone(selected["fy"]["revenue"])
        self.assertEqual(selected["fy"]["net_income"], 5.0)


class SubjectFeatureScreenTests(unittest.TestCase):
    def test_screen_lists_only_universe_members(self) -> None:
        screen = build_subject_feature_screen(
            warehouse_active_ciks=[10, 20, 30],
            mdm_active_ciks=[20, 30, 40],
            period_rows=[
                _period(10, "FY", "2023-12-31", revenue=1.0),  # warehouse only — excluded
                _period(20, "FY", "2023-12-31", revenue=2.0),
                _period(40, "FY", "2023-12-31", revenue=4.0),  # mdm only — excluded
            ],
            watermark_components=_wm(),
        )
        ciks = [row["cik"] for row in screen["rows"]]
        # Universe is 20∩30; both appear even if 30 has no period rows.
        self.assertEqual(ciks, [20, 30])
        self.assertNotIn(10, ciks)
        self.assertNotIn(40, ciks)
        by_cik = {r["cik"]: r for r in screen["rows"]}
        self.assertEqual(by_cik[20]["fy_features_coverage"], COVERAGE_PRESENT)
        self.assertEqual(by_cik[30]["fy_features_coverage"], COVERAGE_UNAVAILABLE)

    def test_coverage_flags_and_contract_version(self) -> None:
        screen = build_subject_feature_screen(
            warehouse_active_ciks=[20],
            mdm_active_ciks=[20],
            period_rows=[
                _period(20, "FY", "2023-12-31", revenue=100.0, net_income=None),
                _period(20, "Q1", "2024-03-31", revenue=25.0),
            ],
            watermark_components=_wm(),
        )
        self.assertEqual(screen["decision_contract_version"], DECISION_CONTRACT_VERSION)
        self.assertIn("decision_watermark_identity", screen)
        self.assertTrue(screen["agent_grade"])
        row = screen["rows"][0]
        self.assertEqual(row["fy_features_coverage"], COVERAGE_PRESENT)
        self.assertEqual(row["interim_features_coverage"], COVERAGE_PRESENT)
        self.assertEqual(row["fy_features"]["revenue"], 100.0)
        self.assertIsNone(row["fy_features"]["net_income"])  # null ≠ zero

    def test_universe_member_without_periods_is_unavailable(self) -> None:
        screen = build_subject_feature_screen(
            warehouse_active_ciks=[99],
            mdm_active_ciks=[99],
            period_rows=[],
            watermark_components=_wm(),
        )
        row = screen["rows"][0]
        self.assertEqual(row["cik"], 99)
        self.assertEqual(row["fy_features_coverage"], COVERAGE_UNAVAILABLE)
        self.assertEqual(row["interim_features_coverage"], COVERAGE_NOT_APPLICABLE)

    def test_fy_only_marks_interim_not_applicable(self) -> None:
        screen = build_subject_feature_screen(
            warehouse_active_ciks=[1],
            mdm_active_ciks=[1],
            period_rows=[_period(1, "FY", "2023-12-31", revenue=10.0)],
            watermark_components=_wm(),
        )
        row = screen["rows"][0]
        self.assertEqual(row["fy_features_coverage"], COVERAGE_PRESENT)
        self.assertEqual(row["interim_features_coverage"], COVERAGE_NOT_APPLICABLE)

    def test_no_market_price_or_pe_fields(self) -> None:
        screen = build_subject_feature_screen(
            warehouse_active_ciks=[1],
            mdm_active_ciks=[1],
            period_rows=[
                _period(
                    1,
                    "FY",
                    "2023-12-31",
                    revenue=10.0,
                    price=99.0,  # must be stripped / ignored
                    pe_ratio=12.0,
                    market_cap=1e9,
                )
            ],
            watermark_components=_wm(),
        )
        row = screen["rows"][0]
        for bad in FORBIDDEN_MARKET_FIELDS:
            self.assertNotIn(bad, row["fy_features"])
            self.assertNotIn(bad, row)
        for key in PURE_SEC_FEATURE_KEYS:
            self.assertIn(key, row["fy_features"])

    def test_fail_closed_watermark_still_returns_screen_but_not_agent_grade(self) -> None:
        screen = build_subject_feature_screen(
            warehouse_active_ciks=[1],
            mdm_active_ciks=[1],
            period_rows=[_period(1, "FY", "2023-12-31", revenue=1.0)],
            watermark_components=_wm(graph_parity_ok=False),
        )
        self.assertFalse(screen["agent_grade"])
        self.assertTrue(screen["rows"])  # rows still available for audit/debug

    def test_empty_fy_metrics_coverage_empty(self) -> None:
        # FY row exists but all pure-SEC keys missing/null → empty not unavailable
        screen = build_subject_feature_screen(
            warehouse_active_ciks=[1],
            mdm_active_ciks=[1],
            period_rows=[_period(1, "FY", "2023-12-31")],
            watermark_components=_wm(),
        )
        self.assertEqual(screen["rows"][0]["fy_features_coverage"], COVERAGE_EMPTY)


if __name__ == "__main__":
    unittest.main()
