"""Ticket 11 — Subject Bundle Read (issuer Trading-Relevant Neighborhood)."""

from __future__ import annotations

import unittest

from edgar_warehouse.serving.decision_contract import DECISION_CONTRACT_VERSION
from edgar_warehouse.serving.subject_bundle_read import (
    EMPLOYMENT_SOURCE_ITEM_502,
    EMPLOYMENT_SOURCE_PROXY,
    SECTION_ADV,
    SECTION_AUDITOR,
    SECTION_EMPLOYMENT,
    SECTION_HOLDERS_OF_SUBJECT,
    SECTION_INSIDERS,
    SECTION_PARENT,
    SECTION_SUBJECT_AS_MANAGER_PORTFOLIO,
    SECTION_SUBJECT_FEATURES,
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


class IssuerSubjectBundleTests(unittest.TestCase):
    def test_bundle_root_has_subject_watermark_and_version(self) -> None:
        bundle = build_issuer_subject_bundle(
            subject_cik=320193,
            watermark_components=_wm(),
        )
        self.assertEqual(bundle["bundle_subject_cik"], 320193)
        self.assertEqual(bundle["bundle_kind"], "issuer")
        self.assertEqual(bundle["decision_contract_version"], DECISION_CONTRACT_VERSION)
        self.assertEqual(
            bundle["decision_watermark_identity"]["gold_run_id"], "gold-1"
        )
        self.assertTrue(bundle["agent_grade"])
        self.assertIn(SECTION_ADV, bundle["sections"])

    def test_adv_not_applicable_for_pure_issuer(self) -> None:
        bundle = build_issuer_subject_bundle(
            subject_cik=1,
            watermark_components=_wm(),
        )
        adv = bundle["sections"][SECTION_ADV]
        self.assertEqual(adv["coverage"], COVERAGE_NOT_APPLICABLE)
        self.assertEqual(adv["rows"], [])

    def test_insiders_require_graph_plus_gold_accession(self) -> None:
        bundle = build_issuer_subject_bundle(
            subject_cik=1,
            watermark_components=_wm(),
            graph_insider_edges=[
                {"person_entity_id": "p1", "person_name": "Ada"},
                {"person_entity_id": "p2", "person_name": "NoGold"},
            ],
            gold_ownership_rows=[
                {
                    "person_entity_id": "p1",
                    "person_name": "Ada",
                    "accession_number": "0001-form4",
                },
                {
                    # gold-only unresolved string — not agent-grade
                    "owner_name": "StringOnly",
                    "accession_number": "0002-form4",
                },
            ],
        )
        insiders = bundle["sections"][SECTION_INSIDERS]
        self.assertEqual(insiders["coverage"], COVERAGE_PRESENT)
        self.assertEqual(len(insiders["rows"]), 1)
        self.assertTrue(insiders["rows"][0]["agent_grade_edge"])
        self.assertEqual(insiders["rows"][0]["source_accessions"], ["0001-form4"])
        self.assertEqual(
            len(insiders["non_agent_grade"]["unresolved_graph_edges"]), 1
        )
        self.assertEqual(
            len(insiders["non_agent_grade"]["gold_only_unresolved"]), 1
        )
        self.assertFalse(
            insiders["non_agent_grade"]["gold_only_unresolved"][0]["agent_grade_edge"]
        )

    def test_insiders_unavailable_when_no_inputs(self) -> None:
        bundle = build_issuer_subject_bundle(
            subject_cik=1,
            watermark_components=_wm(),
        )
        self.assertEqual(
            bundle["sections"][SECTION_INSIDERS]["coverage"], COVERAGE_UNAVAILABLE
        )

    def test_thirteenf_sections_are_separate_with_lag_metadata(self) -> None:
        period = {
            "latest_complete_holdings_period": "2024-03-31",
            "lag_days": 45,
            "as_of_business_date": "2024-06-30",
        }
        bundle = build_issuer_subject_bundle(
            subject_cik=1,
            watermark_components=_wm(),
            holders_of_subject=[{"manager_cik": 99, "cusip": "037833100", "shares": 100}],
            subject_as_manager_portfolio=[
                {"issuer_cusip": "594918104", "shares": 50}
            ],
            holdings_period=period,
        )
        holders = bundle["sections"][SECTION_HOLDERS_OF_SUBJECT]
        book = bundle["sections"][SECTION_SUBJECT_AS_MANAGER_PORTFOLIO]
        self.assertEqual(holders["section"], SECTION_HOLDERS_OF_SUBJECT)
        self.assertEqual(book["section"], SECTION_SUBJECT_AS_MANAGER_PORTFOLIO)
        self.assertEqual(holders["coverage"], COVERAGE_PRESENT)
        self.assertEqual(book["coverage"], COVERAGE_PRESENT)
        self.assertEqual(
            holders["holdings_period"]["latest_complete_holdings_period"],
            "2024-03-31",
        )
        self.assertEqual(holders["holdings_period"]["lag_days"], 45)

    def test_employment_distinguishes_proxy_and_item_502_and_pay(self) -> None:
        bundle = build_issuer_subject_bundle(
            subject_cik=1,
            watermark_components=_wm(),
            employment_edges=[
                {
                    "person_entity_id": "e1",
                    "person_name": "CFO",
                    "source_system": EMPLOYMENT_SOURCE_PROXY,
                    "role_title": "CFO",
                },
                {
                    "person_entity_id": "e2",
                    "person_name": "NewHire",
                    "source_system": EMPLOYMENT_SOURCE_ITEM_502,
                    "role_title": "COO",
                },
            ],
            executive_pay_rows=[
                {
                    "person_name": "CFO",
                    "exec_role": "CFO",
                    "compensation_amount": 1_000_000,
                    "accession_number": "proxy-1",
                }
            ],
        )
        emp = bundle["sections"][SECTION_EMPLOYMENT]
        self.assertEqual(emp["coverage"], COVERAGE_PRESENT)
        sources = {r["source_system"] for r in emp["rows"]}
        self.assertEqual(sources, {EMPLOYMENT_SOURCE_PROXY, EMPLOYMENT_SOURCE_ITEM_502})
        self.assertEqual(emp["executive_pay"][0]["source"], "gold_proxy_executive_record")

    def test_auditor_prefers_pcaob_identity(self) -> None:
        bundle = build_issuer_subject_bundle(
            subject_cik=1,
            watermark_components=_wm(),
            auditor_edges=[
                {"auditor_name": "NoId LLP", "pcaob_id": None},
                {"auditor_name": "Ernst", "pcaob_id": "185"},
            ],
        )
        aud = bundle["sections"][SECTION_AUDITOR]
        self.assertEqual(aud["coverage"], COVERAGE_PRESENT)
        self.assertEqual(aud["rows"][0]["pcaob_id"], "185")
        self.assertEqual(aud["rows"][0]["identity_rule"], "prefer_auditor_evidence_pcaob_id")

    def test_parent_requires_inventory_complete(self) -> None:
        incomplete = build_issuer_subject_bundle(
            subject_cik=1,
            watermark_components=_wm(),
            parent_edges=[{"parent_name": "HoldCo"}],
            parent_inventory_complete=False,
        )
        self.assertEqual(
            incomplete["sections"][SECTION_PARENT]["coverage"], COVERAGE_UNAVAILABLE
        )
        self.assertEqual(incomplete["sections"][SECTION_PARENT]["rows"], [])

        complete_empty = build_issuer_subject_bundle(
            subject_cik=1,
            watermark_components=_wm(),
            parent_edges=[],
            parent_inventory_complete=True,
        )
        self.assertEqual(
            complete_empty["sections"][SECTION_PARENT]["coverage"], COVERAGE_EMPTY
        )

        complete = build_issuer_subject_bundle(
            subject_cik=1,
            watermark_components=_wm(),
            parent_edges=[{"parent_name": "HoldCo", "parent_entity_id": "par1"}],
            parent_inventory_complete=True,
        )
        self.assertEqual(
            complete["sections"][SECTION_PARENT]["coverage"], COVERAGE_PRESENT
        )
        self.assertEqual(
            complete["sections"][SECTION_PARENT]["scope"], "registrant_disclosed"
        )

    def test_subject_features_as_of_and_coverage(self) -> None:
        bundle = build_issuer_subject_bundle(
            subject_cik=1,
            watermark_components=_wm(),
            period_rows=[
                {
                    "cik": 1,
                    "fiscal_period": "FY",
                    "period_end": "2023-12-31",
                    "fiscal_year": 2023,
                    "revenue": 100.0,
                    "net_income": None,
                },
                {
                    "cik": 1,
                    "fiscal_period": "Q1",
                    "period_end": "2024-03-31",
                    "fiscal_year": 2024,
                    "revenue": 30.0,
                },
            ],
        )
        feat = bundle["sections"][SECTION_SUBJECT_FEATURES]
        self.assertEqual(feat["fy_features_coverage"], COVERAGE_PRESENT)
        self.assertEqual(feat["interim_features_coverage"], COVERAGE_PRESENT)
        self.assertIsNone(feat["fy_features"]["net_income"])
        self.assertEqual(feat["fy_features"]["revenue"], 100.0)

    def test_fail_closed_watermark(self) -> None:
        bundle = build_issuer_subject_bundle(
            subject_cik=1,
            watermark_components=_wm(graph_parity_ok=False),
            graph_insider_edges=[{"person_entity_id": "p1"}],
            gold_ownership_rows=[
                {"person_entity_id": "p1", "accession_number": "a1"}
            ],
        )
        self.assertFalse(bundle["agent_grade"])
        self.assertTrue(bundle["sections"][SECTION_INSIDERS]["rows"])

    def test_out_of_universe_subject(self) -> None:
        bundle = build_issuer_subject_bundle(
            subject_cik=999,
            watermark_components=_wm(),
            subject_in_decision_universe=False,
        )
        self.assertFalse(bundle["agent_grade"])
        self.assertEqual(bundle["sections"], {})


if __name__ == "__main__":
    unittest.main()
