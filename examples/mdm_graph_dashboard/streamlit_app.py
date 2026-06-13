from __future__ import annotations

import os
from typing import Any, Mapping

import streamlit as st

from edgar_warehouse.mdm import dashboard_readonly, graph_readonly


SECTIONS = [
    "Overview",
    "MDM Overview",
    "Neo4j Overview",
    "Mismatch Diagnostics",
]
ROW_LIMIT_OPTIONS = [25, 50, 100, 250]
FILTER_ALL = "All"
BOUNDED_SAMPLE_COPY = "Samples are bounded diagnostics, not exhaustive diffs."
FILTERED_EMPTY_HEADING = "No rows match the current filters."
FILTERED_EMPTY_BODY = "Adjust the selected type or row limit, then review the table again."
MDM_CONFIG_REQUIRED_COPY = (
    "MDM configuration is required. Set `MDM_DATABASE_URL`, then restart the dashboard."
)
MDM_UNAVAILABLE_COPY = "MDM database unavailable. Check `MDM_DATABASE_URL`, confirm the database is reachable, and restart the dashboard."
MDM_PERMISSION_DENIED_COPY = "MDM database permission denied. Confirm the configured database user can run read-only SELECT queries."
SNOWFLAKE_GRAPH_UNAVAILABLE_COPY = (
    "Snowflake graph metrics unavailable. MDM overview remains available."
)
SNOWFLAKE_GRAPH_PERMISSION_DENIED_COPY = "Snowflake graph permission denied. Confirm the configured Snowflake role can run read-only graph diagnostics."
NATIVE_APP_FAILURE_COPY = "Snowflake Native App check failed. Run `edgar-warehouse mdm verify-graph` for the acceptance gate and review the remediation below."


@st.cache_data(ttl=60, show_spinner=False)
def _read_mdm_metrics() -> dict[str, Any]:
    return dashboard_readonly.get_mdm_dashboard_metrics().as_dict()


@st.cache_data(ttl=60, show_spinner=False)
def _read_snowflake_graph_metrics(row_limit: int) -> dict[str, Any]:
    return graph_readonly.get_snowflake_graph_metrics(sample_limit=row_limit).as_dict()


def _clear_dashboard_cache() -> None:
    st.cache_data.clear()


def _relationship_types_from_mdm_metrics(payload: Mapping[str, Any]) -> list[str]:
    relationship_counts = payload.get("relationship_counts")
    if isinstance(relationship_counts, Mapping):
        return [str(key) for key in relationship_counts]
    registry = payload.get("registry")
    if isinstance(registry, Mapping):
        relationship_types = registry.get("relationship_types")
        if isinstance(relationship_types, list):
            return [str(value) for value in relationship_types if value]
    return []


def _relationship_types_from_graph_metrics(payload: Mapping[str, Any] | None) -> list[str]:
    if not payload:
        return []
    relationship_types = {
        str(row.get("relationship_type"))
        for row in _mapping_values(payload.get("relationship_comparison"))
        if row.get("relationship_type")
    }
    diagnostics = payload.get("diagnostics")
    if isinstance(diagnostics, Mapping):
        for rows in diagnostics.values():
            for row in _mapping_values(rows):
                if row.get("relationship_type"):
                    relationship_types.add(str(row["relationship_type"]))
    return sorted(relationship_types)


def _relationship_filter_options(
    mdm_metrics: Mapping[str, Any],
    graph_metrics: Mapping[str, Any] | None = None,
) -> list[str]:
    options = {
        *_relationship_types_from_mdm_metrics(mdm_metrics),
        *_relationship_types_from_graph_metrics(graph_metrics),
    }
    return [FILTER_ALL, *sorted(options)]


def _entity_labels_from_mdm_metrics(payload: Mapping[str, Any]) -> list[str]:
    registry = payload.get("registry")
    if not isinstance(registry, Mapping):
        return []
    labels = registry.get("neo4j_labels")
    if isinstance(labels, list):
        return [str(label) for label in labels if label]
    details = registry.get("entity_type_details")
    if isinstance(details, list):
        return [
            str(row.get("neo4j_label"))
            for row in details
            if isinstance(row, Mapping) and row.get("neo4j_label")
        ]
    return []


def _entity_registry_details(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    registry = payload.get("registry")
    if not isinstance(registry, Mapping):
        return []
    details = registry.get("entity_type_details")
    if not isinstance(details, list):
        return []
    return [row for row in details if isinstance(row, Mapping)]


def _entity_types_from_graph_metrics(payload: Mapping[str, Any] | None) -> list[str]:
    if not payload:
        return []
    entity_types = {
        str(row.get("entity_type"))
        for row in _mapping_values(payload.get("entity_comparison"))
        if row.get("entity_type")
    }
    diagnostics = payload.get("diagnostics")
    if isinstance(diagnostics, Mapping):
        for key in ("missing_graph_nodes", "extra_graph_nodes"):
            for row in _mapping_values(diagnostics.get(key)):
                if row.get("entity_type"):
                    entity_types.add(str(row["entity_type"]))
    return sorted(entity_types)


def _entity_filter_options(
    mdm_metrics: Mapping[str, Any],
    graph_metrics: Mapping[str, Any] | None = None,
) -> list[str]:
    options = {
        str(row["entity_type"])
        for row in _entity_registry_details(mdm_metrics)
        if row.get("entity_type")
    }
    if not options:
        options.update(domain for domain, _row in _mapping_items(mdm_metrics.get("entity_counts")))
    options.update(_entity_types_from_graph_metrics(graph_metrics))
    return [FILTER_ALL, *sorted(options)]


def _format_count(value: Any) -> str:
    try:
        return f"{int(value or 0):,}"
    except (TypeError, ValueError):
        return "0"


def _timestamp_caption(label: str, payload: Mapping[str, Any]) -> None:
    last_refreshed = payload.get("last_refreshed")
    if last_refreshed:
        st.caption(f"{label} last refreshed: {last_refreshed}")


def _limit_rows(rows: list[dict[str, Any]], row_limit: int | None) -> list[dict[str, Any]]:
    if row_limit is None:
        return rows
    return rows[:row_limit]


def _render_table_or_empty(
    rows: list[dict[str, Any]],
    *,
    filtered: bool,
    empty_copy: str,
) -> None:
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
        return
    if filtered:
        st.info(FILTERED_EMPTY_HEADING)
        st.caption(FILTERED_EMPTY_BODY)
        return
    st.info(empty_copy)


def _mdm_state_copy(mdm_metrics: Mapping[str, Any]) -> str:
    state = str(mdm_metrics.get("state") or "").lower()
    message = str(mdm_metrics.get("message") or "").lower()
    if state in {"missing_config", "not_configured"} or (
        mdm_metrics.get("error_env_var") == "MDM_DATABASE_URL"
        and not os.environ.get("MDM_DATABASE_URL")
    ):
        return MDM_CONFIG_REQUIRED_COPY
    if "permission" in state or "permission" in message:
        return MDM_PERMISSION_DENIED_COPY
    return MDM_UNAVAILABLE_COPY


def _snowflake_graph_state_copy(graph_metrics: Mapping[str, Any] | None) -> str:
    payload = graph_metrics or {}
    state = str(payload.get("state") or "").lower()
    message = str(payload.get("message") or "").lower()
    if "permission" in state or "permission" in message:
        return SNOWFLAKE_GRAPH_PERMISSION_DENIED_COPY
    return SNOWFLAKE_GRAPH_UNAVAILABLE_COPY


def _render_mdm_unavailable(mdm_metrics: Mapping[str, Any]) -> bool:
    if mdm_metrics.get("available"):
        return False
    st.error(_mdm_state_copy(mdm_metrics))
    return True


def _pending_sync_total(mdm_metrics: Mapping[str, Any]) -> int:
    return sum(
        _int_value(row.get("pending_graph_sync_count"))
        for row in _mapping_values(mdm_metrics.get("relationship_counts"))
    )


def _render_snapshot(
    *,
    mdm_metrics: Mapping[str, Any],
    graph_metrics: Mapping[str, Any] | None,
) -> None:
    entity_total = sum(
        _int_value(row.get("count"))
        for row in _mapping_values(mdm_metrics.get("entity_counts"))
    )
    relationship_total = sum(
        _int_value(row.get("active_count"))
        for row in _mapping_values(mdm_metrics.get("relationship_counts"))
    )
    pending_total = _pending_sync_total(mdm_metrics)
    graph_available = bool(graph_metrics and graph_metrics.get("available"))
    node_total = _int_value((graph_metrics or {}).get("snowflake_graph_nodes"))
    edge_total = _int_value((graph_metrics or {}).get("snowflake_graph_edges"))

    metric_cols = st.columns(5)
    metric_cols[0].metric("MDM entities", _format_count(entity_total), "OK")
    metric_cols[1].metric("MDM relationships", _format_count(relationship_total), "OK")
    metric_cols[2].metric(
        "Snowflake graph nodes",
        _format_count(node_total),
        "OK" if graph_available else "Unavailable",
    )
    metric_cols[3].metric(
        "Snowflake graph edges",
        _format_count(edge_total),
        "OK" if graph_available else "Unavailable",
    )
    metric_cols[4].metric(
        "Pending sync",
        _format_count(pending_total),
        "Review" if pending_total else "OK",
    )


def _render_grouped_warnings(
    *,
    mdm_metrics: Mapping[str, Any],
    graph_metrics: Mapping[str, Any] | None,
) -> None:
    blocking: list[dict[str, str]] = []
    coverage: list[dict[str, str]] = []

    for warning in _mapping_values(mdm_metrics.get("warnings")):
        severity = str(warning.get("severity") or "warning")
        row = {
            "severity": severity,
            "message": str(warning.get("message") or ""),
            "action": str(warning.get("action") or ""),
        }
        if severity == "error":
            blocking.append(row)
        else:
            coverage.append(row)

    if graph_metrics and not graph_metrics.get("available"):
        coverage.append(
            {
                "severity": "warning",
                "message": _snowflake_graph_state_copy(graph_metrics),
                "action": "Check Snowflake connection context and Native App prerequisites outside the dashboard.",
            }
        )

    if _has_graph_mismatches(graph_metrics):
        coverage.append(
            {
                "severity": "warning",
                "message": "Snowflake-hosted graph diagnostics contain mismatches.",
                "action": "Review Mismatch Diagnostics, then run `edgar-warehouse mdm verify-graph` for the acceptance gate.",
            }
        )

    if _native_app_failure_rows(graph_metrics):
        coverage.append(
            {
                "severity": "warning",
                "message": NATIVE_APP_FAILURE_COPY,
                "action": "Review the Native App failure table below.",
            }
        )

    if not blocking and not coverage:
        st.success("No blocking failures or coverage warnings.")
        return

    st.subheader("Attention Needed")
    if blocking:
        st.markdown("**Blocking failures**")
        for row in blocking:
            st.error(f"{row['message']} {row['action']}".strip())
    if coverage:
        st.markdown("**Coverage warnings**")
        for row in coverage:
            if row["severity"] == "info":
                st.info(f"{row['message']} {row['action']}".strip())
            else:
                st.warning(f"{row['message']} {row['action']}".strip())


def _render_entity_table(
    mdm_metrics: Mapping[str, Any],
    *,
    entity_filter: str = FILTER_ALL,
    row_limit: int | None = None,
) -> None:
    rows = [
        {
            "Domain": row.get("label"),
            "Count": _int_value(row.get("count")),
            "Status": row.get("status"),
        }
        for domain, row in _mapping_items(mdm_metrics.get("entity_counts"))
        if entity_filter == FILTER_ALL
        or entity_filter == domain
        or entity_filter == str(row.get("label") or "")
    ]
    _render_table_or_empty(
        _limit_rows(rows, row_limit),
        filtered=entity_filter != FILTER_ALL,
        empty_copy="No MDM entity metrics were returned.",
    )


def _render_mdm_relationship_table(
    *,
    mdm_metrics: Mapping[str, Any],
    relationship_filter: str = FILTER_ALL,
    row_limit: int | None = None,
) -> None:
    rows = []
    for rel_type, row in sorted(_mapping_items(mdm_metrics.get("relationship_counts"))):
        if relationship_filter != FILTER_ALL and relationship_filter != rel_type:
            continue
        rows.append(
            {
                "Relationship Type": rel_type,
                "MDM Active": _int_value(row.get("active_count")),
                "Pending Sync": _int_value(row.get("pending_graph_sync_count")),
                "Status": row.get("status"),
            }
        )
    _render_table_or_empty(
        _limit_rows(rows, row_limit),
        filtered=relationship_filter != FILTER_ALL,
        empty_copy="No active MDM relationship types were returned.",
    )


def _render_entity_comparison(
    *,
    graph_metrics: Mapping[str, Any] | None,
    entity_filter: str = FILTER_ALL,
    row_limit: int | None = None,
) -> None:
    rows = [
        {
            "Entity Type": row.get("entity_type"),
            "MDM Active": _int_value(row.get("mdm_active_count")),
            "Snowflake Graph Nodes": _int_value(row.get("snowflake_graph_node_count")),
            "MDM Minus Graph": _int_value(row.get("mdm_minus_graph")),
            "Graph Minus MDM": _int_value(row.get("graph_minus_mdm")),
            "Status": row.get("status"),
        }
        for row in _mapping_values((graph_metrics or {}).get("entity_comparison"))
        if entity_filter == FILTER_ALL
        or entity_filter == str(row.get("entity_type") or "")
    ]
    st.subheader("Entity Comparison")
    _render_table_or_empty(
        _limit_rows(rows, row_limit),
        filtered=entity_filter != FILTER_ALL,
        empty_copy="No Snowflake graph entity comparison rows were returned.",
    )


def _render_relationship_comparison(
    *,
    graph_metrics: Mapping[str, Any] | None,
    relationship_filter: str = FILTER_ALL,
    row_limit: int | None = None,
) -> None:
    rows = [
        {
            "Relationship Type": row.get("relationship_type"),
            "MDM Active": _int_value(row.get("mdm_active_count")),
            "Snowflake Graph Edges": _int_value(row.get("snowflake_graph_edge_count")),
            "MDM Minus Graph": _int_value(row.get("mdm_minus_graph")),
            "Graph Minus MDM": _int_value(row.get("graph_minus_mdm")),
            "Status": row.get("status"),
        }
        for row in _mapping_values((graph_metrics or {}).get("relationship_comparison"))
        if relationship_filter == FILTER_ALL
        or relationship_filter == str(row.get("relationship_type") or "")
    ]
    st.subheader("Relationship Parity")
    _render_table_or_empty(
        _limit_rows(rows, row_limit),
        filtered=relationship_filter != FILTER_ALL,
        empty_copy="No Snowflake graph relationship comparison rows were returned.",
    )


def _render_diagnostic_samples(
    title: str,
    rows: list[dict[str, Any]],
    *,
    columns: Mapping[str, str],
    entity_filter: str = FILTER_ALL,
    relationship_filter: str = FILTER_ALL,
    row_limit: int | None = None,
) -> None:
    st.subheader(title)
    filtered_rows = []
    for row in rows:
        if entity_filter != FILTER_ALL and row.get("entity_type") != entity_filter:
            continue
        if (
            relationship_filter != FILTER_ALL
            and row.get("relationship_type") != relationship_filter
        ):
            continue
        filtered_rows.append({label: row.get(key) for key, label in columns.items()})
    _render_table_or_empty(
        _limit_rows(filtered_rows, row_limit),
        filtered=entity_filter != FILTER_ALL or relationship_filter != FILTER_ALL,
        empty_copy="No bounded diagnostic sample rows were returned.",
    )


def _render_mismatch_samples(
    *,
    graph_metrics: Mapping[str, Any] | None,
    entity_filter: str = FILTER_ALL,
    relationship_filter: str = FILTER_ALL,
    row_limit: int | None = None,
) -> None:
    diagnostics = (graph_metrics or {}).get("diagnostics")
    if not isinstance(diagnostics, Mapping):
        diagnostics = {}
    st.caption(BOUNDED_SAMPLE_COPY)
    _render_diagnostic_samples(
        "Missing Graph Nodes",
        _mapping_values(diagnostics.get("missing_graph_nodes")),
        columns={"entity_type": "Entity Type", "node_id": "Node ID"},
        entity_filter=entity_filter,
        row_limit=row_limit,
    )
    _render_diagnostic_samples(
        "Extra Graph Nodes",
        _mapping_values(diagnostics.get("extra_graph_nodes")),
        columns={"entity_type": "Entity Type", "node_id": "Node ID"},
        entity_filter=entity_filter,
        row_limit=row_limit,
    )
    _render_diagnostic_samples(
        "Missing Graph Edges",
        _mapping_values(diagnostics.get("missing_graph_edges")),
        columns={"relationship_type": "Relationship Type", "edge_id": "Edge ID"},
        relationship_filter=relationship_filter,
        row_limit=row_limit,
    )
    _render_diagnostic_samples(
        "Extra Graph Edges",
        _mapping_values(diagnostics.get("extra_graph_edges")),
        columns={"relationship_type": "Relationship Type", "edge_id": "Edge ID"},
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
            "missing_source_node": "Missing Source Node",
            "missing_target_node": "Missing Target Node",
            "direction": "Direction",
        },
        relationship_filter=relationship_filter,
        row_limit=row_limit,
    )


def _native_app_failure_rows(
    graph_metrics: Mapping[str, Any] | None,
) -> list[Mapping[str, Any]]:
    native_app = (graph_metrics or {}).get("native_app")
    if not isinstance(native_app, Mapping):
        return []
    return _mapping_values(native_app.get("failing_checks"))


def _render_native_app_failures(graph_metrics: Mapping[str, Any] | None) -> None:
    failing_checks = _native_app_failure_rows(graph_metrics)
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


def _has_graph_mismatches(graph_metrics: Mapping[str, Any] | None) -> bool:
    if not graph_metrics or not graph_metrics.get("available"):
        return False
    for row in _mapping_values(graph_metrics.get("entity_comparison")):
        if _int_value(row.get("mdm_minus_graph")) or _int_value(row.get("graph_minus_mdm")):
            return True
    for row in _mapping_values(graph_metrics.get("relationship_comparison")):
        if _int_value(row.get("mdm_minus_graph")) or _int_value(row.get("graph_minus_mdm")):
            return True
    diagnostics = graph_metrics.get("diagnostics")
    if isinstance(diagnostics, Mapping):
        return any(_mapping_values(rows) for rows in diagnostics.values())
    return False


def _mapping_values(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [row for row in value.values() if isinstance(row, Mapping)]
    if isinstance(value, list):
        return [row for row in value if isinstance(row, Mapping)]
    return []


def _mapping_items(value: Any) -> list[tuple[str, Mapping[str, Any]]]:
    if not isinstance(value, Mapping):
        return []
    return [
        (str(key), row)
        for key, row in value.items()
        if isinstance(row, Mapping)
    ]


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def render_overview(
    *,
    mdm_metrics: Mapping[str, Any],
    graph_metrics: Mapping[str, Any] | None,
) -> None:
    st.title("EdgarTools MDM Graph")
    st.caption(
        "Read-only MDM and Snowflake-hosted graph status. Dashboard refresh is inspection only; `edgar-warehouse mdm verify-graph` remains the acceptance gate."
    )
    if _render_mdm_unavailable(mdm_metrics):
        return
    _render_grouped_warnings(
        mdm_metrics=mdm_metrics,
        graph_metrics=graph_metrics,
    )
    _render_native_app_failures(graph_metrics)
    _render_snapshot(
        mdm_metrics=mdm_metrics,
        graph_metrics=graph_metrics,
    )
    _timestamp_caption("MDM metrics", mdm_metrics)
    if graph_metrics:
        _timestamp_caption("Snowflake graph metrics", graph_metrics)


def render_mdm_overview(*, mdm_metrics: Mapping[str, Any], row_limit: int) -> None:
    st.title("MDM Overview")
    if _render_mdm_unavailable(mdm_metrics):
        return
    entity_filter = st.selectbox("Entity type", _entity_filter_options(mdm_metrics), index=0)
    relationship_filter = st.selectbox("Relationship type", _relationship_filter_options(mdm_metrics), index=0)
    _timestamp_caption("MDM metrics", mdm_metrics)
    _render_entity_table(mdm_metrics, entity_filter=entity_filter, row_limit=row_limit)
    _render_mdm_relationship_table(
        mdm_metrics=mdm_metrics,
        relationship_filter=relationship_filter,
        row_limit=row_limit,
    )


def render_neo4j_overview(
    *,
    mdm_metrics: Mapping[str, Any],
    graph_metrics: Mapping[str, Any] | None,
    row_limit: int,
) -> None:
    st.title("Neo4j Overview")
    st.caption("Snowflake-hosted Neo4j Graph Analytics comparison.")
    if _render_mdm_unavailable(mdm_metrics):
        return
    if graph_metrics and not graph_metrics.get("available"):
        st.info(_snowflake_graph_state_copy(graph_metrics))
        _render_native_app_failures(graph_metrics)
        return
    entity_filter = st.selectbox(
        "Entity type",
        _entity_filter_options(mdm_metrics, graph_metrics),
        index=0,
    )
    relationship_filter = st.selectbox(
        "Relationship type",
        _relationship_filter_options(mdm_metrics, graph_metrics),
        index=0,
    )
    _timestamp_caption("Snowflake graph metrics", graph_metrics or {})
    _render_entity_comparison(
        graph_metrics=graph_metrics,
        entity_filter=entity_filter,
        row_limit=row_limit,
    )
    _render_relationship_comparison(
        graph_metrics=graph_metrics,
        relationship_filter=relationship_filter,
        row_limit=row_limit,
    )
    _render_native_app_failures(graph_metrics)


def render_mismatch_diagnostics(
    *,
    mdm_metrics: Mapping[str, Any],
    graph_metrics: Mapping[str, Any] | None,
    row_limit: int,
) -> None:
    st.title("Mismatch Diagnostics")
    if _render_mdm_unavailable(mdm_metrics):
        return
    if not graph_metrics or not graph_metrics.get("available"):
        st.warning(_snowflake_graph_state_copy(graph_metrics))
    entity_filter = st.selectbox(
        "Entity type",
        _entity_filter_options(mdm_metrics, graph_metrics),
        index=0,
    )
    relationship_filter = st.selectbox(
        "Relationship type",
        _relationship_filter_options(mdm_metrics, graph_metrics),
        index=0,
    )
    _render_relationship_comparison(
        graph_metrics=graph_metrics,
        relationship_filter=relationship_filter,
        row_limit=row_limit,
    )
    _render_mismatch_samples(
        graph_metrics=graph_metrics,
        entity_filter=entity_filter,
        relationship_filter=relationship_filter,
        row_limit=row_limit,
    )
    _render_native_app_failures(graph_metrics)


def main() -> None:
    st.set_page_config(page_title="EdgarTools MDM Graph", layout="wide")
    st.sidebar.title("EdgarTools MDM")
    st.sidebar.caption("Read-only MDM and Snowflake-hosted graph status")
    section_name = st.sidebar.radio("Section", SECTIONS)
    row_limit = st.sidebar.selectbox("Row limit", ROW_LIMIT_OPTIONS, index=1)
    st.sidebar.divider()
    if st.sidebar.button("Refresh metrics", use_container_width=True):
        _clear_dashboard_cache()
        st.rerun()

    mdm_metrics = _read_mdm_metrics()
    graph_metrics = (
        _read_snowflake_graph_metrics(row_limit)
        if mdm_metrics.get("available")
        else None
    )

    if section_name == "Overview":
        render_overview(
            mdm_metrics=mdm_metrics,
            graph_metrics=graph_metrics,
        )
    elif section_name == "MDM Overview":
        render_mdm_overview(mdm_metrics=mdm_metrics, row_limit=row_limit)
    elif section_name == "Neo4j Overview":
        render_neo4j_overview(
            mdm_metrics=mdm_metrics,
            graph_metrics=graph_metrics,
            row_limit=row_limit,
        )
    elif section_name == "Mismatch Diagnostics":
        render_mismatch_diagnostics(
            mdm_metrics=mdm_metrics,
            graph_metrics=graph_metrics,
            row_limit=row_limit,
        )


if __name__ == "__main__":
    main()
