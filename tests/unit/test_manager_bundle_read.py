"""Ticket 12 — Manager bundle ADV / MANAGES_FUND / IS_ENTITY_OF."""

from __future__ import annotations

import unittest

from edgar_warehouse.serving.decision_contract import DECISION_CONTRACT_VERSION
from edgar_warehouse.serving.manager_bundle_read import (
    ADV_SOURCE_BULK_IAPD,
    ADV_SOURCE_HEURISTIC,
    SECTION_IS_ENTITY_OF,
    SECTION_MANAGES_FUND,
    build_adv_section_for_manager,
    build_is_entity_of_section,
    build_manager_subject_bundle,
    build_manages_fund_section,
    issuer_adv_remains_not_applicable,
)
from edgar_warehouse.serving.subject_bundle_read import (
    SECTION_ADV,
    build_issuer_subject_bundle,
)
from edgar_warehouse.serving.subject_feature_screen import (
    COVERAGE_EMPTY,
    COVERAGE_NOT_APPLICABLE,
    COVERAGE_PRESENT,
    COVERAGE_UNAVAILABLE,
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


class ManagesFundSectionTests(unittest.TestCase):
    def test_only_bulk_iapd_is_agent_grade(self) -> None:
        section = build_manages_fund_section(
            [
                {
                    "fund_name": "Fund A",
                    "source_system": ADV_SOURCE_BULK_IAPD,
                    "fund_entity_id": "f1",
                },
                {
                    "fund_name": "Heuristic Fund",
                    "source_system": ADV_SOURCE_HEURISTIC,
                    "fund_entity_id": "f2",
                },
            ]
        )
        self.assertEqual(section["coverage"], COVERAGE_PRESENT)
        self.assertEqual(len(section["rows"]), 1)
        self.assertTrue(section["rows"][0]["agent_grade_edge"])
        self.assertEqual(section["rows"][0]["fund_name"], "Fund A")
        self.assertEqual(len(section["non_agent_grade"]), 1)
        self.assertFalse(section["non_agent_grade"][0]["agent_grade_edge"])
        self.assertEqual(
            section["non_agent_grade"][0]["reason"], "heuristic_adv_not_agent_grade"
        )

    def test_heuristic_only_is_empty_not_present(self) -> None:
        section = build_manages_fund_section(
            [{"fund_name": "H", "source_system": ADV_SOURCE_HEURISTIC}]
        )
        self.assertEqual(section["coverage"], COVERAGE_EMPTY)
        self.assertEqual(section["rows"], [])

    def test_no_inputs_unavailable(self) -> None:
        self.assertEqual(
            build_manages_fund_section([])["coverage"], COVERAGE_UNAVAILABLE
        )


class IsEntityOfTests(unittest.TestCase):
    def test_both_sides_resolved(self) -> None:
        section = build_is_entity_of_section(
            [{"adviser_cik": 111, "company_cik": 222}]
        )
        self.assertEqual(section["coverage"], COVERAGE_PRESENT)
        self.assertEqual(section["rows"][0]["adviser_cik"], 111)
        self.assertEqual(section["rows"][0]["company_cik"], 222)

    def test_sparse_unresolved_does_not_hard_fail(self) -> None:
        section = build_is_entity_of_section(
            [{"adviser_cik": 111, "company_cik": None}]
        )
        self.assertEqual(section["coverage"], COVERAGE_EMPTY)
        self.assertEqual(section["rows"], [])
        self.assertEqual(len(section["unresolved"]), 1)

    def test_zero_edges_unavailable(self) -> None:
        self.assertEqual(
            build_is_entity_of_section([])["coverage"], COVERAGE_UNAVAILABLE
        )


class AdvSectionManagerTests(unittest.TestCase):
    def test_adv_lag_metadata_when_agent_grade(self) -> None:
        section = build_adv_section_for_manager(
            manages_fund_edges=[
                {"fund_name": "F", "source_system": ADV_SOURCE_BULK_IAPD}
            ],
            adv_lag_metadata={"adv_as_of_date": "2024-03-31", "lag_days": 90},
        )
        self.assertEqual(section["coverage"], COVERAGE_PRESENT)
        self.assertIsNotNone(section["adv_lag_metadata"])
        self.assertEqual(section["adv_lag_metadata"]["lag_days"], 90)
        self.assertEqual(
            section["adv_lag_metadata"]["watermark_component"], "adv_bulk_iapd"
        )

    def test_no_lag_block_when_only_heuristic(self) -> None:
        section = build_adv_section_for_manager(
            manages_fund_edges=[
                {"fund_name": "H", "source_system": ADV_SOURCE_HEURISTIC}
            ],
            adv_lag_metadata={"lag_days": 1},
        )
        self.assertEqual(section["coverage"], COVERAGE_EMPTY)
        self.assertIsNone(section["adv_lag_metadata"])


class ManagerBundleTests(unittest.TestCase):
    def test_manager_bundle_shape(self) -> None:
        bundle = build_manager_subject_bundle(
            subject_cik=123,
            watermark_components=_wm(),
            manages_fund_edges=[
                {"fund_name": "F", "source_system": ADV_SOURCE_BULK_IAPD}
            ],
            is_entity_of_edges=[{"adviser_cik": 123, "company_cik": 456}],
            adv_lag_metadata={"adv_as_of_date": "2024-01-01", "lag_days": 10},
        )
        self.assertEqual(bundle["bundle_kind"], "manager")
        self.assertEqual(bundle["decision_contract_version"], DECISION_CONTRACT_VERSION)
        self.assertTrue(bundle["agent_grade"])
        self.assertEqual(
            bundle["sections"][SECTION_MANAGES_FUND]["coverage"], COVERAGE_PRESENT
        )
        self.assertEqual(
            bundle["sections"][SECTION_IS_ENTITY_OF]["coverage"], COVERAGE_PRESENT
        )
        self.assertIsNotNone(bundle["sections"][SECTION_ADV]["adv_lag_metadata"])

    def test_issuer_bundle_adv_still_not_applicable(self) -> None:
        issuer = build_issuer_subject_bundle(
            subject_cik=1,
            watermark_components=_wm(),
        )
        self.assertTrue(issuer_adv_remains_not_applicable(issuer))
        self.assertEqual(
            issuer["sections"][SECTION_ADV]["coverage"], COVERAGE_NOT_APPLICABLE
        )


if __name__ == "__main__":
    unittest.main()
