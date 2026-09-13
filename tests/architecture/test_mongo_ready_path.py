"""Ticket 03: Mongo publisher stays off the aggregator and Agent View."""

from __future__ import annotations

from pathlib import Path

from edgar_warehouse.serving.dashboard_modes import AGENT_VIEW_ALLOWED_OBJECTS
from edgar_warehouse.serving.dashboard_query_registry import AGENT_VIEW_QUERIES

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVING = REPO_ROOT / "edgar_warehouse" / "serving"
CLI = REPO_ROOT / "edgar_warehouse" / "cli.py"
STREAMLIT = REPO_ROOT / "infra" / "snowflake" / "streamlit" / "streamlit_app.py"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

MONGO_WRITE_MARKERS = (
    "mongo_decision_projection",
    "mongo_ready_path",
    "publish_ready_issuer_documents",
    "run_ready_mongo_projection",
    "edgartools_decision",
    "issuer_subject_bundle",
)


def test_observe_only_aggregator_does_not_call_mongo_publisher() -> None:
    source = (SERVING / "watermark_aggregator.py").read_text(encoding="utf-8")
    for marker in MONGO_WRITE_MARKERS:
        assert marker not in source, marker


def test_observe_only_cli_reconcile_does_not_call_mongo_publisher() -> None:
    source = CLI.read_text(encoding="utf-8")
    handler = source.split("def _handle_reconcile_decision_watermark", maxsplit=1)[1]
    handler = handler.split("\ndef ", maxsplit=1)[0]
    for marker in MONGO_WRITE_MARKERS:
        assert marker not in handler, marker


def test_agent_view_reads_snowflake_decision_contract_only() -> None:
    assert set(AGENT_VIEW_QUERIES) == {
        "agent.contract_status",
        "agent.subject_search",
        "agent.subject_bundle",
    }
    for query in AGENT_VIEW_QUERIES.values():
        sql = query.sql.upper()
        assert "EDGARTOOLS_DECISION." in sql
        assert "ISSUER_SUBJECT_BUNDLE" not in sql
        assert "MONGODB" not in sql
        assert "EDGARTOOLS_GOLD." not in sql
    assert "issuer_subject_bundle" not in AGENT_VIEW_ALLOWED_OBJECTS
    assert "subject_feature_screen" not in AGENT_VIEW_ALLOWED_OBJECTS
    streamlit = STREAMLIT.read_text(encoding="utf-8")
    assert "mongo_decision_projection" not in streamlit
    assert "mongo_ready_path" not in streamlit
    assert "edgartools_decision" not in streamlit


def test_ci_has_no_atlas_secrets() -> None:
    offenders: list[str] = []
    for workflow in sorted(WORKFLOWS.glob("*.y*ml")):
        text = workflow.read_text(encoding="utf-8").lower()
        if any(
            token in text
            for token in ("atlas", "mongodb+srv", "mongo_uri", "mongouri")
        ):
            offenders.append(workflow.relative_to(REPO_ROOT).as_posix())
    assert offenders == []
