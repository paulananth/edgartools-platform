from __future__ import annotations

from typing import Any

import streamlit as st

from edgar_warehouse.mdm import dashboard_readonly, graph_readonly


SECTIONS = [
    "Overview",
    "Entities",
    "Relationships",
    "Graph Coverage",
    "Neighborhood",
]
PLACEHOLDER_COPY = (
    "This view is planned for a later phase. Phase 8 only verifies read-only "
    "dashboard connectivity."
)
MDM_EMPTY_HEADING = "No MDM data loaded"
MDM_EMPTY_BODY = "Seed or load the MDM database, then refresh this dashboard."
OPTIONAL_PARTIAL_COPY = "Showing partial data because an optional source is unavailable."
SMOKE_EMPTY_COPY = "No smoke-test rows were returned. Connection checks still completed."


@st.cache_data(ttl=60, show_spinner=False)
def _read_mdm_status() -> dict[str, Any]:
    return dashboard_readonly.check_mdm_status().as_dict()


@st.cache_data(ttl=60, show_spinner=False)
def _read_mdm_smoke() -> dict[str, Any]:
    return dashboard_readonly.run_mdm_smoke_query().as_dict()


@st.cache_data(ttl=60, show_spinner=False)
def _read_neo4j_status() -> dict[str, Any]:
    return graph_readonly.check_neo4j_status().as_dict()


@st.cache_data(ttl=60, show_spinner=False)
def _read_neo4j_smoke() -> dict[str, Any]:
    status, client = graph_readonly.load_neo4j_review_client()
    if client is None:
        return status.as_dict()
    try:
        return graph_readonly.run_neo4j_smoke_query(client=client).as_dict()
    finally:
        client.close()


def _clear_dashboard_cache() -> None:
    st.cache_data.clear()


def _render_status(label: str, status: dict[str, Any], *, required: bool) -> None:
    if status.get("connected"):
        st.success(f"{label}: {status['message']}")
        return
    if required:
        st.error(status["message"])
    else:
        st.warning(status["message"])


def _render_mdm_smoke(smoke: dict[str, Any]) -> None:
    if not smoke.get("available"):
        st.error(smoke["message"])
        return
    rows = smoke.get("rows") or []
    if not rows:
        st.info(MDM_EMPTY_HEADING)
        st.caption(MDM_EMPTY_BODY)
        st.info(SMOKE_EMPTY_COPY)
        return
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_neo4j_smoke(smoke: dict[str, Any]) -> None:
    if smoke.get("connected"):
        st.json({"ok": smoke.get("details", {}).get("ok", False)})
    else:
        st.info(smoke["message"])


def render_overview() -> None:
    st.title("EdgarTools MDM Graph")
    st.caption("Read-only connectivity checks for local MDM and optional Neo4j review.")

    mdm_status = _read_mdm_status()
    neo4j_status = _read_neo4j_status()

    status_left, status_right = st.columns(2)
    with status_left:
        st.subheader("MDM status")
        _render_status("MDM", mdm_status, required=True)
    with status_right:
        st.subheader("Neo4j status")
        _render_status("Neo4j", neo4j_status, required=False)

    if not mdm_status.get("connected"):
        return

    if not neo4j_status.get("connected"):
        st.warning(OPTIONAL_PARTIAL_COPY)

    smoke_left, smoke_right = st.columns(2)
    with smoke_left:
        st.subheader("MDM smoke output")
        _render_mdm_smoke(_read_mdm_smoke())
    with smoke_right:
        st.subheader("Neo4j smoke output")
        _render_neo4j_smoke(_read_neo4j_smoke())


def render_placeholder(section_name: str) -> None:
    st.title(section_name)
    st.info(PLACEHOLDER_COPY)


def main() -> None:
    st.set_page_config(page_title="EdgarTools MDM Graph", layout="wide")
    st.sidebar.title("EdgarTools MDM")
    st.sidebar.caption("Read-only MDM and Neo4j status")
    section_name = st.sidebar.radio("Section", SECTIONS)
    st.sidebar.divider()
    if st.sidebar.button("Refresh data", use_container_width=True):
        _clear_dashboard_cache()
        st.rerun()

    if section_name == "Overview":
        render_overview()
    else:
        render_placeholder(section_name)


if __name__ == "__main__":
    main()
