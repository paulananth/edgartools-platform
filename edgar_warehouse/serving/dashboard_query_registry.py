"""Authoritative query registry for the Snowflake audit dashboard.

Agent View queries are deliberately closed-world: every query has a stable ID,
declares exactly one approved Decision Contract/status object, and is checked
against :mod:`dashboard_modes` before SQL is returned.  Explore queries remain
outside this registry because they are explicitly labelled, unrestricted
research reads.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    from edgar_warehouse.serving.dashboard_modes import (
        MODE_AGENT_VIEW,
        assert_query_allowed,
    )
except ImportError:  # pragma: no cover - Streamlit-in-Snowflake flat stage
    from dashboard_modes import MODE_AGENT_VIEW, assert_query_allowed


@dataclass(frozen=True)
class DashboardQuery:
    query_id: str
    object_name: str
    sql: str
    max_rows: int


AGENT_VIEW_QUERIES: dict[str, DashboardQuery] = {
    "agent.contract_status": DashboardQuery(
        query_id="agent.contract_status",
        object_name="DECISION_CONTRACT_DISPLAY_STATUS",
        sql="""
            select
              readiness_state, not_ready_reason, decision_contract_version,
              decision_watermark,
              business_date,
              gold_updated_at,
              graph_generation_id,
              graph_activated_at,
              coverage_state,
              alignment_status
            from EDGARTOOLS_DECISION.DECISION_CONTRACT_DISPLAY_STATUS
            limit 1
        """,
        max_rows=1,
    ),
    "agent.subject_search": DashboardQuery(
        query_id="agent.subject_search",
        object_name="SUBJECT_BUNDLE_DISPLAY_ISSUER",
        sql="""
            select
              cik, entity_name, tickers, sic, sic_description, readiness_state, not_ready_reason,
              state_of_incorporation, fiscal_year_end,
              decision_contract_version, decision_watermark,
              business_date, graph_generation_id, coverage_state,
              alignment_status
            from EDGARTOOLS_DECISION.SUBJECT_BUNDLE_DISPLAY_ISSUER
            where entity_name ilike ? or tickers ilike ?
            order by entity_name, cik
            limit 25
        """,
        max_rows=25,
    ),
    "agent.subject_bundle": DashboardQuery(
        query_id="agent.subject_bundle",
        object_name="SUBJECT_BUNDLE_DISPLAY_ISSUER",
        sql="""
            select *
            from EDGARTOOLS_DECISION.SUBJECT_BUNDLE_DISPLAY_ISSUER
            where cik = ?
            limit 1
        """,
        max_rows=1,
    ),
}


def registered_query(query_id: str) -> DashboardQuery:
    """Return an Agent View query only after enforcing the mode policy."""
    try:
        query = AGENT_VIEW_QUERIES[query_id]
    except KeyError as exc:
        raise KeyError(f"unregistered dashboard query: {query_id}") from exc
    assert_query_allowed(MODE_AGENT_VIEW, query.object_name)
    return query


__all__ = ["AGENT_VIEW_QUERIES", "DashboardQuery", "registered_query"]
