"""Ticket 13 — Streamlit Agent View vs Explore mode gating."""

from __future__ import annotations

import unittest

from edgar_warehouse.serving.dashboard_modes import (
    AGENT_VIEW_ALLOWED_OBJECTS,
    AGENT_VIEW_BANNER,
    EXPLORE_BANNER,
    MODE_AGENT_VIEW,
    MODE_EXPLORE,
    SESSION_MODE_KEY,
    assert_query_allowed,
    dual_mode_cik_context,
    is_explore_labeled_not_for_agent,
    is_object_allowed,
    mode_banner,
    normalize_mode,
    persist_inspected_cik,
    persist_mode,
    resolve_session_mode,
)


class DashboardModeTests(unittest.TestCase):
    def test_normalize_and_default_agent_view(self) -> None:
        self.assertEqual(normalize_mode("Explore"), MODE_EXPLORE)
        self.assertEqual(normalize_mode(None), MODE_AGENT_VIEW)
        self.assertEqual(resolve_session_mode({}), MODE_AGENT_VIEW)

    def test_session_mode_sticky(self) -> None:
        state: dict = {}
        persist_mode(state, MODE_EXPLORE)
        self.assertEqual(state[SESSION_MODE_KEY], MODE_EXPLORE)
        self.assertEqual(resolve_session_mode(state), MODE_EXPLORE)
        # explicit selection overrides sticky
        self.assertEqual(
            resolve_session_mode(state, selected=MODE_AGENT_VIEW), MODE_AGENT_VIEW
        )

    def test_agent_view_blocks_free_gold(self) -> None:
        self.assertFalse(is_object_allowed(MODE_AGENT_VIEW, "FINANCIAL_FACTORS"))
        self.assertFalse(is_object_allowed(MODE_AGENT_VIEW, "EDGARTOOLS_GOLD.COMPANY"))
        with self.assertRaises(PermissionError):
            assert_query_allowed(MODE_AGENT_VIEW, "OWNERSHIP_HOLDINGS")

    def test_agent_view_allows_contract_objects(self) -> None:
        for name in (
            "SUBJECT_FEATURE_SCREEN",
            "SUBJECT_BUNDLE_READ_ISSUER",
            "DECISION_WATERMARK",
        ):
            self.assertTrue(is_object_allowed(MODE_AGENT_VIEW, name), name)
            assert_query_allowed(MODE_AGENT_VIEW, name)
        self.assertIn("SUBJECT_FEATURE_SCREEN", AGENT_VIEW_ALLOWED_OBJECTS)

    def test_explore_allows_gold_but_is_labeled(self) -> None:
        self.assertTrue(is_object_allowed(MODE_EXPLORE, "FINANCIAL_FACTORS"))
        self.assertTrue(is_object_allowed(MODE_EXPLORE, "COMPANY"))
        self.assertTrue(is_explore_labeled_not_for_agent(MODE_EXPLORE))
        banner = mode_banner(MODE_EXPLORE)
        self.assertEqual(banner, EXPLORE_BANNER)
        self.assertIn("Not", banner)
        self.assertIn("Trading Decision", banner)

    def test_agent_view_banner(self) -> None:
        self.assertEqual(mode_banner(MODE_AGENT_VIEW), AGENT_VIEW_BANNER)
        self.assertIn("Decision Contract", AGENT_VIEW_BANNER)

    def test_same_cik_both_modes(self) -> None:
        state: dict = {}
        persist_inspected_cik(state, 320193)
        agent = dual_mode_cik_context(state, mode=MODE_AGENT_VIEW, cik=320193)
        explore = dual_mode_cik_context(state, mode=MODE_EXPLORE, cik=320193)
        self.assertEqual(agent["cik"], explore["cik"])
        self.assertTrue(agent["contract_only"])
        self.assertFalse(explore["contract_only"])
        self.assertTrue(agent["audit_comparison_supported"])
        self.assertTrue(explore["audit_comparison_supported"])
        self.assertEqual(agent["session_cik"], 320193)


if __name__ == "__main__":
    unittest.main()
