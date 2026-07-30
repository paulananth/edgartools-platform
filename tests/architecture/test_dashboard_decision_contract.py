from __future__ import annotations

from pathlib import Path

from edgar_warehouse.serving.dashboard_query_registry import (
    AGENT_VIEW_QUERIES,
    registered_query,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_SQL = (
    REPO_ROOT
    / "infra"
    / "snowflake"
    / "sql"
    / "decision_contract"
    / "03_dashboard_contract.sql"
)
FEATURE_SCREEN_SQL = CONTRACT_SQL.with_name("01_subject_feature_screen.sql")


def test_every_agent_query_is_registered_bounded_and_contract_scoped() -> None:
    assert set(AGENT_VIEW_QUERIES) == {
        "agent.contract_status",
        "agent.subject_search",
        "agent.subject_bundle",
    }
    for query_id, query in AGENT_VIEW_QUERIES.items():
        assert registered_query(query_id) is query
        assert query.max_rows <= 25
        assert " limit " in f" {query.sql.lower()} "
        assert "EDGARTOOLS_GOLD." not in query.sql.upper()
        assert "NEO4J_GRAPH_MIGRATION." not in query.sql.upper()


def test_contract_views_fail_closed_on_publication_and_active_generation() -> None:
    sql = CONTRACT_SQL.read_text(encoding="utf-8").upper()
    assert "DECISION_CONTRACT_PUBLICATION" in sql
    assert "PUBLICATION_STATUS = 'READY'" in sql
    assert "ALIGNMENT_STATUS = 'ALIGNED'" in sql
    assert "PTR.ACTIVE_GENERATION_ID = P.GRAPH_GENERATION_ID" in sql
    assert "LOWER(COALESCE(C.TRACKING_STATUS, '')) = 'ACTIVE'" in sql
    assert "JOIN ACTIVE_GRAPH_SUBJECT" in sql


def test_feature_screen_uses_tracked_active_subjects_not_all_gold_companies() -> None:
    sql = FEATURE_SCREEN_SQL.read_text(encoding="utf-8").upper()
    assert "TRACKING_STATUS" in sql
    assert "= 'ACTIVE'" in sql
    assert "PLACEHOLDER" not in sql
    assert "MIRRORS WAREHOUSE_ACTIVE" not in sql


def test_reader_gets_only_public_contract_views() -> None:
    sql = CONTRACT_SQL.read_text(encoding="utf-8").upper()
    grants = [line.strip() for line in sql.splitlines() if line.strip().startswith("GRANT SELECT")]
    assert len(grants) == 3
    assert not any("DECISION_CONTRACT_PUBLICATION" in grant for grant in grants)
    assert not any("MDM_GRAPH_" in grant for grant in grants)
