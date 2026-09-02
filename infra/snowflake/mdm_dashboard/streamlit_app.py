"""EdgarTools MDM/graph review dashboard (Streamlit-in-Snowflake).

GH-252: hosted port of the local operator dashboard
(examples/mdm_graph_dashboard/streamlit_app.py). Reads exclusively from
GH-251's generation-scoped review contract (MDM_GRAPH_REVIEW schema, 5
fail-closed views -- infra/snowflake/sql/graph_review/01_graph_review_contract.sql)
through the active Snowpark session -- no MDM Postgres DSN, no direct Neo4j
credential, no MDM_SNOWFLAKE_*/DBT_SNOWFLAKE_* service credential.

The local dashboard's separate "MDM Overview" section (backed by a direct
Postgres query -- pending_graph_sync_count, the neo4j_labels/entity_type_details
registry, live MDM-only warnings) has no equivalent here by design: those
fields are not part of GH-251's published contract, and this app must not
fabricate placeholder values for them. Scope confirmed in the GH-252 issue
comment ("drop those fields entirely" rather than default to 0). "MDM
Overview" and "Neo4j Overview" also collapse into one "Parity" section here,
since without the Postgres-only registry both sections would otherwise show
the same entity/relationship parity data under different names.

Mismatch samples and native-app checks reflect whatever generation
``edgar-warehouse mdm reconcile`` last published -- this dashboard never
re-runs verification itself (GH-251 criterion 5: refresh happens only from
graph_review_publish.py, called by the CLI). The "Row limit" control below
is a client-side display truncation of already-published, already-bounded
rows, not a live re-query knob -- unlike the local dashboard, which reruns
the verifier with a fresh sample_limit on each row-limit change.
"""

from __future__ import annotations

from typing import Any, Mapping

import streamlit as st
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="EdgarTools MDM Graph Review", layout="wide")

REVIEW_SCHEMA = "MDM_GRAPH_REVIEW"
SECTIONS = ["Overview", "Parity", "Mismatch Diagnostics"]
ROW_LIMIT_OPTIONS = [25, 50, 100, 250]
FILTER_ALL = "All"

BOUNDED_SAMPLE_COPY = (
    "Samples are bounded diagnostics captured at the last "
    "`edgar-warehouse mdm reconcile` run, not a live or exhaustive diff."
)
FILTERED_EMPTY_HEADING = "No rows match the current filters."
FILTERED_EMPTY_BODY = "Adjust the selected type or row limit, then review the table again."
NO_ACTIVE_GENERATION_COPY = (
    "No generation has ever been activated in this environment, or the active "
    "generation has no published review rows yet. Run "
    "`edgar-warehouse mdm reconcile` against this environment, then refresh."
)
REVIEW_UNAVAILABLE_COPY = (
    "MDM graph review data unavailable. Confirm this app's role has SELECT on "
    "the MDM_GRAPH_REVIEW views (EDGARTOOLS_GRAPH_REVIEW_READER) and retry."
)
NATIVE_APP_FAILURE_COPY = (
    "Snowflake Native App check failed. Run `edgar-warehouse mdm reconcile` "
    "for the acceptance gate and review the remediation below."
)


# ---------------------------------------------------------------------------
# Data layer -- Snowpark queries against GH-251's 5 fail-closed views.
# ---------------------------------------------------------------------------


def _query(session: Any, sql: str) -> list[dict[str, Any]]:
    return [row.as_dict() for row in session.sql(sql).collect()]


@st.cache_data(ttl=60, show_spinner=False)
def _read_graph_review_metrics() -> dict[str, Any]:
    session = get_active_session()
    try:
        generation_rows = _query(
            session,
            f"SELECT * FROM {REVIEW_SCHEMA}.V_GRAPH_REVIEW_ACTIVE_GENERATION",
        )
    except Exception as exc:  # noqa: BLE001 -- surfaced to the UI, not re-raised
        return _unavailable_metrics(str(exc))

    if not generation_rows:
        return _no_active_generation_metrics()

    try:
        entity_rows = _query(
            session, f"SELECT * FROM {REVIEW_SCHEMA}.V_GRAPH_REVIEW_ENTITY_PARITY"
        )
        relationship_rows = _query(
            session, f"SELECT * FROM {REVIEW_SCHEMA}.V_GRAPH_REVIEW_RELATIONSHIP_PARITY"
        )
        mismatch_rows = _query(
            session, f"SELECT * FROM {REVIEW_SCHEMA}.V_GRAPH_REVIEW_MISMATCH_SAMPLE"
        )
        native_app_rows = _query(
            session, f"SELECT * FROM {REVIEW_SCHEMA}.V_GRAPH_REVIEW_NATIVE_APP_CHECK"
        )
    except Exception as exc:  # noqa: BLE001
        return _unavailable_metrics(str(exc))

    return _metrics_from_rows(
        generation=generation_rows[0],
        entity_rows=entity_rows,
        relationship_rows=relationship_rows,
        mismatch_rows=mismatch_rows,
        native_app_rows=native_app_rows,
    )


def _clear_dashboard_cache() -> None:
    st.cache_data.clear()


def _empty_diagnostics() -> dict[str, list[dict[str, Any]]]:
    return {
        "missing_graph_nodes": [],
        "extra_graph_nodes": [],
        "missing_graph_edges": [],
        "extra_graph_edges": [],
        "missing_graph_edge_endpoints": [],
    }


def _entity_comparison_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "entity_type": str(row.get("ENTITY_TYPE") or ""),
            "mdm_active_count": _int_value(row.get("MDM_ACTIVE_COUNT")),
            "snowflake_graph_node_count": _int_value(row.get("GRAPH_NODE_COUNT")),
            "mdm_minus_graph": _int_value(row.get("MDM_MINUS_GRAPH")),
            "graph_minus_mdm": _int_value(row.get("GRAPH_MINUS_MDM")),
            "status": str(row.get("STATUS") or ""),
        }
        for row in rows
    ]


def _relationship_comparison_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "relationship_type": str(row.get("RELATIONSHIP_TYPE") or ""),
            "mdm_active_count": _int_value(row.get("MDM_ACTIVE_COUNT")),
            "snowflake_graph_edge_count": _int_value(row.get("GRAPH_EDGE_COUNT")),
            "mdm_minus_graph": _int_value(row.get("MDM_MINUS_GRAPH")),
            "graph_minus_mdm": _int_value(row.get("GRAPH_MINUS_MDM")),
            "status": str(row.get("STATUS") or ""),
        }
        for row in rows
    ]


def _diagnostics_from_mismatch_rows(
    rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    diagnostics = _empty_diagnostics()
    for row in rows:
        sample_type = str(row.get("SAMPLE_TYPE") or "")
        if sample_type in ("missing_graph_nodes", "extra_graph_nodes"):
            diagnostics[sample_type].append(
                {
                    "entity_type": str(row.get("ENTITY_TYPE") or ""),
                    "node_id": str(row.get("NODE_ID") or ""),
                }
            )
        elif sample_type in ("missing_graph_edges", "extra_graph_edges"):
            diagnostics[sample_type].append(
                {
                    "relationship_type": str(row.get("RELATIONSHIP_TYPE") or ""),
                    "edge_id": str(row.get("EDGE_ID") or ""),
                }
            )
        elif sample_type == "missing_graph_edge_endpoints":
            diagnostics[sample_type].append(
                {
                    "relationship_type": str(row.get("RELATIONSHIP_TYPE") or ""),
                    "edge_id": str(row.get("EDGE_ID") or ""),
                    "source_node_id": str(row.get("SOURCE_NODE_ID") or ""),
                    "target_node_id": str(row.get("TARGET_NODE_ID") or ""),
                }
            )
    return diagnostics


def _native_app_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    checks = [
        {
            "check": str(row.get("CHECK_NAME") or ""),
            "status": str(row.get("STATUS") or ""),
            "detail": str(row.get("DETAIL") or ""),
            "remediation": str(row.get("REMEDIATION") or "")
            or "Review hosted graph prerequisites.",
        }
        for row in rows
    ]
    failing_checks = [check for check in checks if check["status"].lower() != "ok"]
    if not checks:
        overall_status = "unavailable"
    elif failing_checks:
        overall_status = "failed"
    else:
        overall_status = "ok"
    return {"status": overall_status, "failing_checks": failing_checks}


def _metrics_from_rows(
    *,
    generation: dict[str, Any],
    entity_rows: list[dict[str, Any]],
    relationship_rows: list[dict[str, Any]],
    mismatch_rows: list[dict[str, Any]],
    native_app_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "available": True,
        "state": "ok",
        "message": "Graph review metrics loaded.",
        "target": {
            "generation_id": _stringify(generation.get("GENERATION_ID")),
            "activated_at": _stringify(generation.get("ACTIVATED_AT")),
            "verified_at": _stringify(generation.get("VERIFIED_AT")),
            "rule_version": _stringify(generation.get("RULE_VERSION")),
            "schema_version": _stringify(generation.get("SCHEMA_VERSION")),
        },
        "snowflake_graph_nodes": _int_value(generation.get("NODE_COUNT")),
        "snowflake_graph_edges": _int_value(generation.get("EDGE_COUNT")),
        "entity_comparison": _entity_comparison_rows(entity_rows),
        "relationship_comparison": _relationship_comparison_rows(relationship_rows),
        "diagnostics": _diagnostics_from_mismatch_rows(mismatch_rows),
        "native_app": _native_app_from_rows(native_app_rows),
    }


def _unavailable_metrics(message: str) -> dict[str, Any]:
    return {
        "available": False,
        "state": "unavailable",
        "message": message,
        "target": {},
        "snowflake_graph_nodes": 0,
        "snowflake_graph_edges": 0,
        "entity_comparison": [],
        "relationship_comparison": [],
        "diagnostics": _empty_diagnostics(),
        "native_app": {"status": "unavailable", "failing_checks": []},
    }


def _no_active_generation_metrics() -> dict[str, Any]:
    metrics = _unavailable_metrics(NO_ACTIVE_GENERATION_COPY)
    metrics["state"] = "no_active_generation"
    return metrics


def _stringify(value: Any) -> str | None:
    return str(value) if value is not None else None


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _format_count(value: Any) -> str:
    return f"{_int_value(value):,}"


# ---------------------------------------------------------------------------
# Filter option helpers -- derived purely from the published rows, no
# separate registry source (there isn't one in this app).
# ---------------------------------------------------------------------------


def _mapping_values(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, Mapping)]
    return []


def _entity_filter_options(metrics: Mapping[str, Any]) -> list[str]:
    options = {
        str(row.get("entity_type"))
        for row in _mapping_values(metrics.get("entity_comparison"))
        if row.get("entity_type")
    }
    diagnostics = metrics.get("diagnostics")
    if isinstance(diagnostics, Mapping):
        for key in ("missing_graph_nodes", "extra_graph_nodes"):
            for row in _mapping_values(diagnostics.get(key)):
                if row.get("entity_type"):
                    options.add(str(row["entity_type"]))
    return [FILTER_ALL, *sorted(options)]


def _relationship_filter_options(metrics: Mapping[str, Any]) -> list[str]:
    options = {
        str(row.get("relationship_type"))
        for row in _mapping_values(metrics.get("relationship_comparison"))
        if row.get("relationship_type")
    }
    diagnostics = metrics.get("diagnostics")
    if isinstance(diagnostics, Mapping):
        for key in ("missing_graph_edges", "extra_graph_edges", "missing_graph_edge_endpoints"):
            for row in _mapping_values(diagnostics.get(key)):
                if row.get("relationship_type"):
                    options.add(str(row["relationship_type"]))
    return [FILTER_ALL, *sorted(options)]


def _limit_rows(rows: list[dict[str, Any]], row_limit: int) -> list[dict[str, Any]]:
    return rows[:row_limit]


def _render_table_or_empty(
    rows: list[dict[str, Any]], *, filtered: bool, empty_copy: str
) -> None:
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
        return
    if filtered:
        st.info(FILTERED_EMPTY_HEADING)
        st.caption(FILTERED_EMPTY_BODY)
        return
    st.info(empty_copy)


def _render_unavailable(metrics: Mapping[str, Any]) -> bool:
    if metrics.get("available"):
        return False
    st.error(str(metrics.get("message") or REVIEW_UNAVAILABLE_COPY))
    return True


def _has_graph_mismatches(metrics: Mapping[str, Any]) -> bool:
    for row in _mapping_values(metrics.get("entity_comparison")):
        if _int_value(row.get("mdm_minus_graph")) or _int_value(row.get("graph_minus_mdm")):
            return True
    for row in _mapping_values(metrics.get("relationship_comparison")):
        if _int_value(row.get("mdm_minus_graph")) or _int_value(row.get("graph_minus_mdm")):
            return True
    diagnostics = metrics.get("diagnostics")
    if isinstance(diagnostics, Mapping):
        return any(_mapping_values(rows) for rows in diagnostics.values())
    return False


def _native_app_failure_rows(metrics: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    native_app = metrics.get("native_app")
    if not isinstance(native_app, Mapping):
        return []
    return _mapping_values(native_app.get("failing_checks"))


def _render_native_app_failures(metrics: Mapping[str, Any]) -> None:
    failing_checks = _native_app_failure_rows(metrics)
    if not failing_checks:
        return
    st.subheader("Snowflake Native App Failures")
    st.warning(NATIVE_APP_FAILURE_COPY)
    rows = [
        {
            "Check": row.get("check"),
            "Status": row.get("status"),
            "Detail": row.get("detail"),
            "Remediation": row.get("remediation"),
        }
        for row in failing_checks
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_generation_caption(metrics: Mapping[str, Any]) -> None:
    target = metrics.get("target")
    if not isinstance(target, Mapping) or not target.get("generation_id"):
        return
    st.caption(
        f"Active generation: `{target.get('generation_id')}` "
        f"(activated {target.get('activated_at')}, "
        f"last verified {target.get('verified_at')})"
    )


# ---------------------------------------------------------------------------
# Sections.
# ---------------------------------------------------------------------------


def render_overview(metrics: Mapping[str, Any]) -> None:
    st.title("EdgarTools MDM Graph Review")
    st.caption(
        "Read-only Snowflake-hosted graph review status, published by "
        "`edgar-warehouse mdm reconcile`. This dashboard is inspection "
        "only; verify-graph remains the acceptance gate."
    )
    if _render_unavailable(metrics):
        return
    _render_generation_caption(metrics)
    _render_native_app_failures(metrics)

    node_total = metrics.get("snowflake_graph_nodes")
    edge_total = metrics.get("snowflake_graph_edges")
    mismatches = _has_graph_mismatches(metrics)

    metric_cols = st.columns(2)
    metric_cols[0].metric("Snowflake graph nodes", _format_count(node_total))
    metric_cols[1].metric("Snowflake graph edges", _format_count(edge_total))

    if mismatches:
        st.warning(
            "Parity mismatches present in the active generation. Review the "
            "Parity and Mismatch Diagnostics sections."
        )
    elif not _native_app_failure_rows(metrics):
        st.success("No parity mismatches or Native App failures in the active generation.")


def render_parity(metrics: Mapping[str, Any], *, row_limit: int) -> None:
    st.title("Parity")
    st.caption("MDM-active counts vs. the Snowflake-hosted graph, for the active generation.")
    if _render_unavailable(metrics):
        return
    entity_filter = st.selectbox("Entity type", _entity_filter_options(metrics), index=0)
    relationship_filter = st.selectbox(
        "Relationship type", _relationship_filter_options(metrics), index=0
    )
    _render_generation_caption(metrics)

    entity_rows = [
        {
            "Entity Type": row.get("entity_type"),
            "MDM Active": _int_value(row.get("mdm_active_count")),
            "Snowflake Graph Nodes": _int_value(row.get("snowflake_graph_node_count")),
            "MDM Minus Graph": _int_value(row.get("mdm_minus_graph")),
            "Graph Minus MDM": _int_value(row.get("graph_minus_mdm")),
            "Status": row.get("status"),
        }
        for row in _mapping_values(metrics.get("entity_comparison"))
        if entity_filter == FILTER_ALL or entity_filter == str(row.get("entity_type") or "")
    ]
    st.subheader("Entity Comparison")
    _render_table_or_empty(
        _limit_rows(entity_rows, row_limit),
        filtered=entity_filter != FILTER_ALL,
        empty_copy="No entity comparison rows were returned.",
    )

    relationship_rows = [
        {
            "Relationship Type": row.get("relationship_type"),
            "MDM Active": _int_value(row.get("mdm_active_count")),
            "Snowflake Graph Edges": _int_value(row.get("snowflake_graph_edge_count")),
            "MDM Minus Graph": _int_value(row.get("mdm_minus_graph")),
            "Graph Minus MDM": _int_value(row.get("graph_minus_mdm")),
            "Status": row.get("status"),
        }
        for row in _mapping_values(metrics.get("relationship_comparison"))
        if relationship_filter == FILTER_ALL
        or relationship_filter == str(row.get("relationship_type") or "")
    ]
    st.subheader("Relationship Parity")
    _render_table_or_empty(
        _limit_rows(relationship_rows, row_limit),
        filtered=relationship_filter != FILTER_ALL,
        empty_copy="No relationship comparison rows were returned.",
    )

    _render_native_app_failures(metrics)


def _render_diagnostic_samples(
    title: str,
    rows: list[dict[str, Any]],
    *,
    columns: Mapping[str, str],
    entity_filter: str,
    relationship_filter: str,
    row_limit: int,
) -> None:
    st.subheader(title)
    filtered_rows = []
    for row in rows:
        if entity_filter != FILTER_ALL and row.get("entity_type") != entity_filter:
            continue
        if relationship_filter != FILTER_ALL and row.get("relationship_type") != relationship_filter:
            continue
        filtered_rows.append({label: row.get(key) for key, label in columns.items()})
    _render_table_or_empty(
        _limit_rows(filtered_rows, row_limit),
        filtered=entity_filter != FILTER_ALL or relationship_filter != FILTER_ALL,
        empty_copy="No bounded diagnostic sample rows were returned.",
    )


def render_mismatch_diagnostics(metrics: Mapping[str, Any], *, row_limit: int) -> None:
    st.title("Mismatch Diagnostics")
    if _render_unavailable(metrics):
        return
    entity_filter = st.selectbox("Entity type", _entity_filter_options(metrics), index=0)
    relationship_filter = st.selectbox(
        "Relationship type", _relationship_filter_options(metrics), index=0
    )
    _render_generation_caption(metrics)
    st.caption(BOUNDED_SAMPLE_COPY)

    diagnostics = metrics.get("diagnostics")
    if not isinstance(diagnostics, Mapping):
        diagnostics = _empty_diagnostics()

    _render_diagnostic_samples(
        "Missing Graph Nodes",
        _mapping_values(diagnostics.get("missing_graph_nodes")),
        columns={"entity_type": "Entity Type", "node_id": "Node ID"},
        entity_filter=entity_filter,
        relationship_filter=FILTER_ALL,
        row_limit=row_limit,
    )
    _render_diagnostic_samples(
        "Extra Graph Nodes",
        _mapping_values(diagnostics.get("extra_graph_nodes")),
        columns={"entity_type": "Entity Type", "node_id": "Node ID"},
        entity_filter=entity_filter,
        relationship_filter=FILTER_ALL,
        row_limit=row_limit,
    )
    _render_diagnostic_samples(
        "Missing Graph Edges",
        _mapping_values(diagnostics.get("missing_graph_edges")),
        columns={"relationship_type": "Relationship Type", "edge_id": "Edge ID"},
        entity_filter=FILTER_ALL,
        relationship_filter=relationship_filter,
        row_limit=row_limit,
    )
    _render_diagnostic_samples(
        "Extra Graph Edges",
        _mapping_values(diagnostics.get("extra_graph_edges")),
        columns={"relationship_type": "Relationship Type", "edge_id": "Edge ID"},
        entity_filter=FILTER_ALL,
        relationship_filter=relationship_filter,
        row_limit=row_limit,
    )
    _render_diagnostic_samples(
        "Missing Graph Edge Endpoints",
        _mapping_values(diagnostics.get("missing_graph_edge_endpoints")),
        columns={
            "relationship_type": "Relationship Type",
            "edge_id": "Edge ID",
            "source_node_id": "Source Node ID",
            "target_node_id": "Target Node ID",
        },
        entity_filter=FILTER_ALL,
        relationship_filter=relationship_filter,
        row_limit=row_limit,
    )
    _render_native_app_failures(metrics)


def main() -> None:
    st.sidebar.title("EdgarTools MDM Graph")
    st.sidebar.caption("Read-only, generation-scoped graph review (GH-251/GH-252)")
    section_name = st.sidebar.radio("Section", SECTIONS)
    row_limit = st.sidebar.selectbox("Row limit", ROW_LIMIT_OPTIONS, index=1)
    st.sidebar.divider()
    if st.sidebar.button("Refresh metrics", use_container_width=True):
        _clear_dashboard_cache()
        st.rerun()

    metrics = _read_graph_review_metrics()

    if section_name == "Overview":
        render_overview(metrics)
    elif section_name == "Parity":
        render_parity(metrics, row_limit=row_limit)
    elif section_name == "Mismatch Diagnostics":
        render_mismatch_diagnostics(metrics, row_limit=row_limit)


# Streamlit / SiS provide session_state; unit tests inject a fake streamlit
# without it -- see infra/snowflake/streamlit/streamlit_app.py for why this
# is used instead of `if __name__ == "__main__"` (the SiS runtime does not
# reliably set __name__ to "__main__" when executing a staged app).
if hasattr(st, "session_state"):
    main()
