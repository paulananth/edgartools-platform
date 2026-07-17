"""Streamlit-in-Snowflake Agent View vs Explore modes (ticket 13 / ADR 0001).

Pure mode-gating logic unit-tested without Streamlit. The SiS app imports these
helpers so Agent View cannot run unlabeled free gold joins, and Explore is
always labeled not-for-agent / not Trading Decision input.
"""

from __future__ import annotations

from typing import Any, Mapping

MODE_AGENT_VIEW = "agent_view"
MODE_EXPLORE = "explore"
DASHBOARD_MODES = frozenset({MODE_AGENT_VIEW, MODE_EXPLORE})

# Session-state key for sticky mode within a Streamlit session
SESSION_MODE_KEY = "edgartools_dashboard_mode"
SESSION_CIK_KEY = "edgartools_inspected_cik"

# Decision Contract objects Agent View may query (ticket 10/11 surfaces + status)
AGENT_VIEW_ALLOWED_OBJECTS = frozenset(
    {
        "SUBJECT_FEATURE_SCREEN",
        "SUBJECT_BUNDLE_READ",
        "SUBJECT_BUNDLE_READ_ISSUER",
        "SUBJECT_BUNDLE_READ_MANAGER",
        "DECISION_WATERMARK",
        "DECISION_CONTRACT_STATUS",
        "BUNDLE_HOLDERS_OF_SUBJECT",
        "BUNDLE_AUDITOR",
        "EDGARTOOLS_GOLD_STATUS",  # freshness only, not free gold joins
    }
)

EXPLORE_BANNER = (
    "Explore Mode — free gold / SOURCE queries for research. "
    "**Not** the agent Decision Contract and **not** Trading Decision input."
)

AGENT_VIEW_BANNER = (
    "Agent View — Decision Contract objects only "
    "(Subject Feature Screen / Subject Bundle Read / watermark). "
    "Same surface a trading agent would pin."
)


def normalize_mode(value: str | None) -> str:
    raw = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if raw in {"agent", "agent_view", "agentview"}:
        return MODE_AGENT_VIEW
    if raw in {"explore", "explore_mode", "research"}:
        return MODE_EXPLORE
    return MODE_AGENT_VIEW  # default fail-closed to contract-only


def resolve_session_mode(
    session_state: Mapping[str, Any],
    *,
    selected: str | None = None,
) -> str:
    """Sticky session mode: explicit selection wins, else prior session, else agent_view."""
    if selected is not None and str(selected).strip():
        return normalize_mode(str(selected))
    existing = session_state.get(SESSION_MODE_KEY)
    if existing is not None:
        return normalize_mode(str(existing))
    return MODE_AGENT_VIEW


def persist_mode(session_state: dict[str, Any], mode: str) -> str:
    resolved = normalize_mode(mode)
    session_state[SESSION_MODE_KEY] = resolved
    return resolved


def persist_inspected_cik(session_state: dict[str, Any], cik: int | None) -> None:
    if cik is None:
        session_state.pop(SESSION_CIK_KEY, None)
        return
    session_state[SESSION_CIK_KEY] = int(cik)


def inspected_cik(session_state: Mapping[str, Any]) -> int | None:
    val = session_state.get(SESSION_CIK_KEY)
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def is_object_allowed(mode: str, object_name: str) -> bool:
    """Whether a logical warehouse object may be queried in this mode."""
    mode_n = normalize_mode(mode)
    name = str(object_name or "").strip().upper()
    if mode_n == MODE_EXPLORE:
        return True  # free gold allowed, but must be labeled in UI
    # Agent View: contract allowlist only
    bare = name.split(".")[-1]
    return bare in AGENT_VIEW_ALLOWED_OBJECTS or name in AGENT_VIEW_ALLOWED_OBJECTS


def assert_query_allowed(mode: str, object_name: str) -> None:
    if not is_object_allowed(mode, object_name):
        raise PermissionError(
            f"Agent View cannot query {object_name!r}; "
            f"allowed contract objects: {sorted(AGENT_VIEW_ALLOWED_OBJECTS)}"
        )


def mode_banner(mode: str) -> str:
    if normalize_mode(mode) == MODE_EXPLORE:
        return EXPLORE_BANNER
    return AGENT_VIEW_BANNER


def is_explore_labeled_not_for_agent(mode: str) -> bool:
    """Explore mode always carries the not-for-agent label in its banner."""
    return normalize_mode(mode) == MODE_EXPLORE and "not" in EXPLORE_BANNER.lower()


def dual_mode_cik_context(
    session_state: Mapping[str, Any],
    *,
    mode: str,
    cik: int,
) -> dict[str, Any]:
    """Same CIK inspectable in both modes for audit comparison."""
    return {
        "cik": int(cik),
        "mode": normalize_mode(mode),
        "banner": mode_banner(mode),
        "contract_only": normalize_mode(mode) == MODE_AGENT_VIEW,
        "session_cik": inspected_cik(session_state),
        "audit_comparison_supported": True,
    }
