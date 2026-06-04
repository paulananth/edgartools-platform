from __future__ import annotations

from typing import Any, Mapping

import streamlit as st

from edgar_warehouse.mdm import dashboard_readonly, graph_readonly


SECTIONS = [
    "Overview",
    "MDM Overview",
    "Neo4j Overview",
    "Mismatch Diagnostics",
]
BOUNDED_SAMPLE_COPY = "Samples are bounded diagnostics, not exhaustive diffs."


@st.cache_data(ttl=60, show_spinner=False)
def _read_mdm_metrics() -> dict[str, Any]:
    return dashboard_readonly.get_mdm_dashboard_metrics().as_dict()


@st.cache_data(ttl=60, show_spinner=False)
def _read_mdm_diagnostic_inputs() -> dict[str, Any]:
    return dashboard_readonly.get_active_relationship_diagnostic_inputs().as_dict()


@st.cache_data(ttl=60, show_spinner=False)
def _read_neo4j_metrics(
    mdm_metrics: Mapping[str, Any],
    mdm_diagnostic_inputs: Mapping[str, Any],
) -> dict[str, Any]:
    relationship_types = _relationship_types_from_mdm_metrics(mdm_metrics)
    entity_labels = _entity_labels_from_mdm_metrics(mdm_metrics)
    return graph_readonly.get_neo4j_graph_metrics(
        entity_labels=entity_labels,
        relationship_types=relationship_types,
        mdm_diagnostic_inputs=mdm_diagnostic_inputs,
    ).as_dict()


def _clear_dashboard_cache() -> None:
    st.cache_data.clear()


def _relationship_types_from_mdm_metrics(payload: Mapping[str, Any]) -> list[str]:
    relationship_counts = payload.get("relationship_counts")
    if isinstance(relationship_counts, Mapping):
        return [str(key) for key in relationship_counts]
    return []


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


def _neo4j_label_for_entity(
    *,
    mdm_metrics: Mapping[str, Any],
    domain: str,
    entity_row: Mapping[str, Any],
) -> str:
    explicit_label = entity_row.get("neo4j_label")
    if explicit_label:
        return str(explicit_label)
    for detail in _entity_registry_details(mdm_metrics):
        if str(detail.get("entity_type") or "") == domain and detail.get("neo4j_label"):
            return str(detail["neo4j_label"])
    return domain


def _format_count(value: Any) -> str:
    try:
        return f"{int(value or 0):,}"
    except (TypeError, ValueError):
        return "0"


def _format_percent(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "-"


def _timestamp_caption(label: str, payload: Mapping[str, Any]) -> None:
    last_refreshed = payload.get("last_refreshed")
    if last_refreshed:
        st.caption(f"{label} last refreshed: {last_refreshed}")


def _render_mdm_unavailable(mdm_metrics: Mapping[str, Any]) -> bool:
    if mdm_metrics.get("available"):
        return False
    st.error(mdm_metrics.get("message", "MDM database unavailable."))
    _render_grouped_warnings(mdm_metrics=mdm_metrics, neo4j_metrics=None, coverage_rows=[])
    return True


def _render_snapshot(
    *,
    mdm_metrics: Mapping[str, Any],
    neo4j_metrics: Mapping[str, Any] | None,
    coverage_rows: list[dict[str, Any]],
) -> None:
    entity_total = sum(
        int(row.get("count") or 0)
        for row in _mapping_values(mdm_metrics.get("entity_counts"))
    )
    relationship_total = sum(
        int(row.get("active_count") or 0)
        for row in _mapping_values(mdm_metrics.get("relationship_counts"))
    )
    pending_total = sum(
        int(row.get("pending_graph_sync_count") or 0)
        for row in _mapping_values(mdm_metrics.get("relationship_counts"))
    )
    node_total = 0
    edge_total = 0
    if neo4j_metrics and neo4j_metrics.get("available"):
        node_total = sum(
            int(row.get("node_count") or 0)
            for row in _mapping_values(neo4j_metrics.get("node_counts"))
        )
        edge_total = sum(
            int(row.get("edge_count") or 0)
            for row in _mapping_values(neo4j_metrics.get("relationship_counts"))
        )

    missing_total = sum(int(row.get("missing_estimate") or 0) for row in coverage_rows)
    extra_total = sum(int(row.get("extra_graph_count") or 0) for row in coverage_rows)
    neo_status = "OK" if neo4j_metrics and neo4j_metrics.get("available") else "Unavailable"
    relationship_status = "OK"
    if missing_total:
        relationship_status = "Missing graph data"
    elif extra_total:
        relationship_status = "Extra graph data"
    elif pending_total:
        relationship_status = "Pending sync"

    metric_cols = st.columns(5)
    metric_cols[0].metric("MDM entities", _format_count(entity_total), "OK")
    metric_cols[1].metric("MDM relationships", _format_count(relationship_total), relationship_status)
    metric_cols[2].metric("Neo4j nodes", _format_count(node_total), neo_status)
    metric_cols[3].metric("Neo4j edges", _format_count(edge_total), neo_status)
    metric_cols[4].metric("Pending sync", _format_count(pending_total), "Review" if pending_total else "OK")


def _render_grouped_warnings(
    *,
    mdm_metrics: Mapping[str, Any],
    neo4j_metrics: Mapping[str, Any] | None,
    coverage_rows: list[dict[str, Any]],
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

    if neo4j_metrics and not neo4j_metrics.get("available"):
        coverage.append(
            {
                "severity": "warning",
                "message": str(neo4j_metrics.get("message") or "Neo4j graph metrics unavailable."),
                "action": "Check graph configuration and network access outside the dashboard.",
            }
        )

    for row in coverage_rows:
        if int(row.get("missing_estimate") or 0) > 0:
            coverage.append(
                {
                    "severity": "warning",
                    "message": f"{row['relationship_type']} has missing graph data.",
                    "action": "Review pending and missing-edge samples.",
                }
            )
        if int(row.get("extra_graph_count") or 0) > 0:
            coverage.append(
                {
                    "severity": "warning",
                    "message": f"{row['relationship_type']} has extra graph data.",
                    "action": "Review extra graph samples against the MDM registry.",
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


def _render_entity_table(mdm_metrics: Mapping[str, Any]) -> None:
    rows = [
        {
            "Domain": row.get("label"),
            "Count": int(row.get("count") or 0),
            "Status": row.get("status"),
        }
        for row in _mapping_values(mdm_metrics.get("entity_counts"))
    ]
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No MDM entity metrics were returned.")


def _render_relationship_table(
    *,
    mdm_metrics: Mapping[str, Any],
    neo4j_metrics: Mapping[str, Any] | None,
) -> None:
    neo4j_relationships = (
        neo4j_metrics.get("relationship_counts", {})
        if neo4j_metrics and neo4j_metrics.get("available")
        else {}
    )
    rows = []
    for rel_type, row in sorted(_mapping_items(mdm_metrics.get("relationship_counts"))):
        graph_row = neo4j_relationships.get(rel_type, {}) if isinstance(neo4j_relationships, Mapping) else {}
        rows.append(
            {
                "Relationship Type": rel_type,
                "MDM Active": int(row.get("active_count") or 0),
                "Pending Sync": int(row.get("pending_graph_sync_count") or 0),
                "Neo4j Edges": _format_count(graph_row.get("edge_count")) if graph_row else "-",
                "Status": row.get("status"),
            }
        )
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No active MDM relationship types were returned.")


def _render_entity_comparison(
    *,
    mdm_metrics: Mapping[str, Any],
    neo4j_metrics: Mapping[str, Any] | None,
) -> None:
    node_counts = (
        neo4j_metrics.get("node_counts", {})
        if neo4j_metrics and neo4j_metrics.get("available")
        else {}
    )
    detail_rows: list[dict[str, Any]] = []
    chart_rows: list[dict[str, Any]] = []
    for domain, row in _mapping_items(mdm_metrics.get("entity_counts")):
        label = str(row.get("label") or domain)
        graph_key = _neo4j_label_for_entity(
            mdm_metrics=mdm_metrics,
            domain=domain,
            entity_row=row,
        )
        graph_count = 0
        if isinstance(node_counts, Mapping):
            graph_count = int((node_counts.get(graph_key) or {}).get("node_count") or 0)
        mdm_count = int(row.get("count") or 0)
        detail_rows.append(
            {
                "Domain": label,
                "MDM Count": mdm_count,
                "Neo4j Label": graph_key,
                "Neo4j Count": graph_count if neo4j_metrics and neo4j_metrics.get("available") else "-",
                "Status": "Unavailable" if not (neo4j_metrics and neo4j_metrics.get("available")) else "OK",
            }
        )
        chart_rows.append({"Domain": label, "Source": "MDM", "Count": mdm_count})
        if neo4j_metrics and neo4j_metrics.get("available"):
            chart_rows.append({"Domain": label, "Source": "Neo4j", "Count": graph_count})

    st.subheader("Entity Domain Coverage")
    if chart_rows:
        st.bar_chart(chart_rows, x="Domain", y="Count", color="Source")
    if detail_rows:
        st.dataframe(detail_rows, use_container_width=True, hide_index=True)


def _relationship_coverage_rows(
    *,
    mdm_metrics: Mapping[str, Any],
    neo4j_metrics: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    neo4j_relationships = (
        neo4j_metrics.get("relationship_counts", {})
        if neo4j_metrics and neo4j_metrics.get("available")
        else {}
    )
    return [
        row.as_dict()
        for row in dashboard_readonly.build_relationship_coverage_rows(
            mdm_metrics.get("relationship_counts", {}),
            neo4j_relationships if isinstance(neo4j_relationships, Mapping) else {},
        )
    ]


def _render_relationship_coverage(rows: list[dict[str, Any]]) -> None:
    table_rows = [
        {
            "Relationship Type": row.get("relationship_type"),
            "MDM Active": int(row.get("mdm_active_count") or 0),
            "Neo4j Edges": int(row.get("neo4j_edge_count") or 0),
            "Pending Sync": int(row.get("pending_graph_sync_count") or 0),
            "Missing Estimate": int(row.get("missing_estimate") or 0),
            "Coverage": _format_percent(row.get("coverage_percent")),
            "Status": row.get("status"),
        }
        for row in rows
    ]
    st.subheader("Relationship Coverage")
    if table_rows:
        st.dataframe(table_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No relationship coverage rows were returned.")


def _render_samples(title: str, rows: list[dict[str, Any]]) -> None:
    st.subheader(title)
    st.caption(BOUNDED_SAMPLE_COPY)
    if not rows:
        st.info("No bounded sample rows were returned.")
        return
    display_rows = [
        {
            "Relationship Type": row.get("relationship_type"),
            "Source": row.get("source_entity_name") or row.get("source_entity_id"),
            "Target": row.get("target_entity_name") or row.get("target_entity_id"),
            "Created": row.get("created_at", "-"),
        }
        for row in rows
    ]
    st.dataframe(display_rows, use_container_width=True, hide_index=True)


def _flatten_sample_map(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(payload, Mapping):
        for samples in payload.values():
            if isinstance(samples, list):
                rows.extend(row for row in samples if isinstance(row, Mapping))
    return rows


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


def render_overview(
    *,
    mdm_metrics: Mapping[str, Any],
    neo4j_metrics: Mapping[str, Any] | None,
    coverage_rows: list[dict[str, Any]],
) -> None:
    st.title("EdgarTools MDM Graph")
    st.caption("Read-only MDM and Neo4j coverage review.")
    if _render_mdm_unavailable(mdm_metrics):
        return
    _render_grouped_warnings(
        mdm_metrics=mdm_metrics,
        neo4j_metrics=neo4j_metrics,
        coverage_rows=coverage_rows,
    )
    _render_snapshot(
        mdm_metrics=mdm_metrics,
        neo4j_metrics=neo4j_metrics,
        coverage_rows=coverage_rows,
    )
    _timestamp_caption("MDM metrics", mdm_metrics)
    if neo4j_metrics:
        _timestamp_caption("Neo4j metrics", neo4j_metrics)


def render_mdm_overview(*, mdm_metrics: Mapping[str, Any]) -> None:
    st.title("MDM Overview")
    if _render_mdm_unavailable(mdm_metrics):
        return
    _timestamp_caption("MDM metrics", mdm_metrics)
    _render_entity_table(mdm_metrics)
    _render_relationship_table(mdm_metrics=mdm_metrics, neo4j_metrics=None)


def render_neo4j_overview(
    *,
    mdm_metrics: Mapping[str, Any],
    neo4j_metrics: Mapping[str, Any] | None,
) -> None:
    st.title("Neo4j Overview")
    if _render_mdm_unavailable(mdm_metrics):
        return
    if neo4j_metrics and not neo4j_metrics.get("available"):
        st.info(neo4j_metrics.get("message", "Neo4j graph metrics unavailable."))
        return
    _timestamp_caption("Neo4j metrics", neo4j_metrics or {})
    _render_entity_comparison(mdm_metrics=mdm_metrics, neo4j_metrics=neo4j_metrics)
    _render_relationship_table(mdm_metrics=mdm_metrics, neo4j_metrics=neo4j_metrics)


def render_mismatch_diagnostics(
    *,
    mdm_metrics: Mapping[str, Any],
    neo4j_metrics: Mapping[str, Any] | None,
    coverage_rows: list[dict[str, Any]],
) -> None:
    st.title("Mismatch Diagnostics")
    if _render_mdm_unavailable(mdm_metrics):
        return
    if not neo4j_metrics or not neo4j_metrics.get("available"):
        st.warning(
            (neo4j_metrics or {}).get(
                "message",
                "Neo4j graph metrics unavailable. MDM metrics are still available.",
            )
        )
    _render_entity_comparison(mdm_metrics=mdm_metrics, neo4j_metrics=neo4j_metrics)
    _render_relationship_coverage(coverage_rows)
    _render_samples("Pending Sync Samples", list(mdm_metrics.get("pending_sync_samples") or []))
    if neo4j_metrics and neo4j_metrics.get("available"):
        _render_samples(
            "Missing Edge Samples",
            _flatten_sample_map(neo4j_metrics.get("missing_edge_samples")),
        )
        _render_samples(
            "Extra Graph Data Samples",
            _flatten_sample_map(neo4j_metrics.get("extra_graph_samples")),
        )


def main() -> None:
    st.set_page_config(page_title="EdgarTools MDM Graph", layout="wide")
    st.sidebar.title("EdgarTools MDM")
    st.sidebar.caption("Read-only MDM and Neo4j status")
    section_name = st.sidebar.radio("Section", SECTIONS)
    st.sidebar.divider()
    if st.sidebar.button("Refresh metrics", use_container_width=True):
        _clear_dashboard_cache()
        st.rerun()

    mdm_metrics = _read_mdm_metrics()
    mdm_diagnostic_inputs = (
        _read_mdm_diagnostic_inputs() if mdm_metrics.get("available") else {}
    )
    neo4j_metrics = (
        _read_neo4j_metrics(mdm_metrics, mdm_diagnostic_inputs)
        if mdm_metrics.get("available")
        else None
    )
    coverage_rows = _relationship_coverage_rows(
        mdm_metrics=mdm_metrics,
        neo4j_metrics=neo4j_metrics,
    )

    if section_name == "Overview":
        render_overview(
            mdm_metrics=mdm_metrics,
            neo4j_metrics=neo4j_metrics,
            coverage_rows=coverage_rows,
        )
    elif section_name == "MDM Overview":
        render_mdm_overview(mdm_metrics=mdm_metrics)
    elif section_name == "Neo4j Overview":
        render_neo4j_overview(mdm_metrics=mdm_metrics, neo4j_metrics=neo4j_metrics)
    elif section_name == "Mismatch Diagnostics":
        render_mismatch_diagnostics(
            mdm_metrics=mdm_metrics,
            neo4j_metrics=neo4j_metrics,
            coverage_rows=coverage_rows,
        )


if __name__ == "__main__":
    main()
