"""Ticket 09: Decision Watermark and Agent-Grade gate."""

from __future__ import annotations

import unittest

from edgar_warehouse.serving.decision_contract import (
    DECISION_CONTRACT_VERSION,
    evaluate_agent_grade,
)


class DecisionContractTests(unittest.TestCase):
    def _ok_components(self, **overrides):
        base = {
            "business_date": "2024-06-01",
            "gold_run_id": "gold-abc",
            "graph_generation_id": "gen-1",
            "silver_completeness_ok": True,
            "graph_parity_ok": True,
            "high_severity_reconcile_open": False,
            "bronze_persist_used": False,
        }
        base.update(overrides)
        return base

    def test_agent_grade_pass(self) -> None:
        result = evaluate_agent_grade(self._ok_components())
        self.assertTrue(result.agent_grade)
        self.assertEqual(result.decision_contract_version, DECISION_CONTRACT_VERSION)
        self.assertEqual(result.reasons, ())
        self.assertIsNotNone(result.watermark)
        self.assertEqual(result.watermark.gold_run_id, "gold-abc")

    def test_fail_closed_missing_graph(self) -> None:
        result = evaluate_agent_grade(self._ok_components(graph_generation_id=""))
        self.assertFalse(result.agent_grade)
        self.assertTrue(any("graph_generation" in r for r in result.reasons))

    def test_fail_closed_parity(self) -> None:
        result = evaluate_agent_grade(self._ok_components(graph_parity_ok=False))
        self.assertFalse(result.agent_grade)
        self.assertTrue(any("parity" in r for r in result.reasons))

    def test_fail_closed_reconcile_unless_waived(self) -> None:
        result = evaluate_agent_grade(
            self._ok_components(high_severity_reconcile_open=True, reconcile_waived=False)
        )
        self.assertFalse(result.agent_grade)
        waived = evaluate_agent_grade(
            self._ok_components(high_severity_reconcile_open=True, reconcile_waived=True)
        )
        self.assertTrue(waived.agent_grade)

    def test_bronze_hashes_only_when_persist_used(self) -> None:
        result = evaluate_agent_grade(
            self._ok_components(bronze_persist_used=True, bronze_content_hashes=())
        )
        self.assertFalse(result.agent_grade)
        ok = evaluate_agent_grade(
            self._ok_components(
                bronze_persist_used=True,
                bronze_content_hashes=("abc",),
            )
        )
        self.assertTrue(ok.agent_grade)
        # Hashes without persist flag is also fail-closed (misconfiguration)
        bad = evaluate_agent_grade(
            self._ok_components(
                bronze_persist_used=False,
                bronze_content_hashes=("abc",),
            )
        )
        self.assertFalse(bad.agent_grade)

    def test_to_dict_shape(self) -> None:
        d = evaluate_agent_grade(self._ok_components()).to_dict()
        self.assertIn("agent_grade", d)
        self.assertIn("decision_contract_version", d)
        self.assertIn("watermark", d)
        self.assertIn("gold_run_id", d["watermark"])


if __name__ == "__main__":
    unittest.main()
