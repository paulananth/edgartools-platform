"""GH-251: persist ``mdm verify-graph``'s payload into the generation-scoped
Snowflake graph-review contract.

The contract (bounded, read-only tables + views a managed dashboard can
query through a plain Snowpark session -- no MDM Postgres DSN, no direct
Neo4j credential, no MDM_SNOWFLAKE_*/DBT_SNOWFLAKE_* service credential) is
defined in ``infra/snowflake/sql/graph_review/01_graph_review_contract.sql``
(not applied to live Snowflake by this module -- see that file and the
landing PR for what still needs a deliberate live-apply step).

Refresh happens only from this module, called by ``mdm verify-graph``'s CLI
handler -- never from dashboard interaction (GH-251 criterion 5). Writes are
DELETE + INSERT scoped to one ``GENERATION_ID`` (idempotent re-publish of
the same generation; never touches another generation's rows), mirroring
the additive-publish pattern :class:`~edgar_warehouse.mdm.snowflake_graph.
SnowflakeGraphSyncExecutor.sync` already uses for
``MDM_GRAPH_NODES``/``MDM_GRAPH_EDGES``.

Counts/parity/samples/checks published here come directly from the same
``SnowflakeGraphVerificationResult.payload`` the verifier already computed
-- this module runs no independent comparison query, so reconciliation to
"authoritative graph verification for the same generation" (GH-251
criterion 4) holds by construction, not as something this module separately
proves.
"""

from __future__ import annotations

from typing import Any

from edgar_warehouse.mdm.snowflake_graph import _sql_literal

DEFAULT_REVIEW_SCHEMA = "MDM_GRAPH_REVIEW"
DEFAULT_GRAPH_SCHEMA = "NEO4J_GRAPH_MIGRATION"

_MISMATCH_SAMPLE_KINDS = (
    "missing_graph_nodes",
    "extra_graph_nodes",
    "missing_graph_edges",
    "extra_graph_edges",
    "missing_graph_edge_endpoints",
)


class GraphReviewPublishError(RuntimeError):
    """Raised when publishing review rows fails.

    Deliberately a distinct exception type from anything ``verify()``
    raises: the CLI handler (``mdm verify-graph``) must be able to tell
    "the graph parity check itself failed" apart from "verification
    succeeded but we couldn't publish the audit rows" and choose different
    handling for each -- conflating the two would make a review-publish
    outage look like a graph-integrity failure, or vice versa.
    """


def resolve_active_generation_id(
    connection: Any,
    *,
    database: str,
    graph_schema: str = DEFAULT_GRAPH_SCHEMA,
) -> str | None:
    """The generation ``GRAPH_ACTIVE_POINTER`` currently points at.

    Returns ``None`` if no generation has ever been activated (a fresh
    environment) -- callers should treat that as "nothing to publish yet",
    not as an error.
    """
    # Deliberately not edgar_warehouse.mdm.snowflake_graph._fetch_scalar --
    # that helper coerces its result with int(), which is correct for the
    # row/edge counts it was written for but would corrupt or crash on this
    # string-valued GENERATION_ID column.
    cursor = connection.cursor()
    try:
        result = cursor.execute(
            f"SELECT ACTIVE_GENERATION_ID FROM {database}.{graph_schema}.GRAPH_ACTIVE_POINTER "
            "WHERE POINTER_ID = 'active'"
        )
        fetch_source = result if hasattr(result, "fetchone") else cursor
        row = fetch_source.fetchone()
    finally:
        cursor.close()
    if not row:
        return None
    value = row[0] if not isinstance(row, dict) else row.get("ACTIVE_GENERATION_ID")
    return str(value) if value else None


def publish_graph_review(
    connection: Any,
    *,
    database: str,
    payload: dict[str, Any],
    generation_id: str,
    review_schema: str = DEFAULT_REVIEW_SCHEMA,
) -> None:
    """Persist one verify-graph ``payload`` for one ``generation_id``.

    Raises :class:`GraphReviewPublishError` on any failure -- including the
    review schema/tables not existing yet, e.g. before
    ``01_graph_review_contract.sql`` has been applied to an environment.
    Callers decide what that should mean for their own exit code; this
    function never silently swallows a failure into a no-op.
    """
    if not generation_id:
        raise GraphReviewPublishError(
            "generation_id is required to publish graph review rows"
        )

    statements = _render_publish_statements(
        database=database,
        review_schema=review_schema,
        payload=payload,
        generation_id=generation_id,
    )
    cursor = connection.cursor()
    try:
        for statement in statements:
            try:
                cursor.execute(statement)
            except Exception as exc:
                raise GraphReviewPublishError(
                    f"failed to publish graph review rows for generation "
                    f"{generation_id!r}: {exc}"
                ) from exc
    finally:
        cursor.close()


def _render_publish_statements(
    *,
    database: str,
    review_schema: str,
    payload: dict[str, Any],
    generation_id: str,
) -> list[str]:
    gid = _sql_literal(generation_id)
    statements: list[str] = []

    entity_table = f"{database}.{review_schema}.GRAPH_REVIEW_ENTITY_PARITY"
    statements.append(f"DELETE FROM {entity_table} WHERE GENERATION_ID = {gid}")
    for row in (payload.get("node_parity") or {}).get("by_entity_type") or []:
        statements.append(
            f"INSERT INTO {entity_table} "
            "(GENERATION_ID, ENTITY_TYPE, MDM_ACTIVE_COUNT, GRAPH_NODE_COUNT, "
            "MDM_MINUS_GRAPH, GRAPH_MINUS_MDM, STATUS) VALUES ("
            f"{gid}, {_sql_literal(str(row.get('entity_type') or ''))}, "
            f"{_int(row.get('mdm_active_count'))}, "
            f"{_int(row.get('snowflake_graph_node_count'))}, "
            f"{_int(row.get('mdm_minus_graph'))}, {_int(row.get('graph_minus_mdm'))}, "
            f"{_sql_literal(_parity_status(row))})"
        )

    relationship_table = f"{database}.{review_schema}.GRAPH_REVIEW_RELATIONSHIP_PARITY"
    statements.append(f"DELETE FROM {relationship_table} WHERE GENERATION_ID = {gid}")
    for row in (payload.get("relationship_parity") or {}).get("by_relationship_type") or []:
        statements.append(
            f"INSERT INTO {relationship_table} "
            "(GENERATION_ID, RELATIONSHIP_TYPE, MDM_ACTIVE_COUNT, GRAPH_EDGE_COUNT, "
            "MDM_MINUS_GRAPH, GRAPH_MINUS_MDM, STATUS) VALUES ("
            f"{gid}, {_sql_literal(str(row.get('relationship_type') or ''))}, "
            f"{_int(row.get('mdm_active_count'))}, "
            f"{_int(row.get('snowflake_graph_edge_count'))}, "
            f"{_int(row.get('mdm_minus_graph'))}, {_int(row.get('graph_minus_mdm'))}, "
            f"{_sql_literal(_parity_status(row))})"
        )

    sample_table = f"{database}.{review_schema}.GRAPH_REVIEW_MISMATCH_SAMPLE"
    statements.append(f"DELETE FROM {sample_table} WHERE GENERATION_ID = {gid}")
    diagnostics = payload.get("diagnostics") or {}
    for sample_type in _MISMATCH_SAMPLE_KINDS:
        for row in diagnostics.get(sample_type) or []:
            statements.append(
                _render_mismatch_sample_insert(sample_table, gid, sample_type, row)
            )

    native_table = f"{database}.{review_schema}.GRAPH_REVIEW_NATIVE_APP_CHECK"
    statements.append(f"DELETE FROM {native_table} WHERE GENERATION_ID = {gid}")
    native_app = payload.get("native_app") or {}
    for check in native_app.get("checks") or []:
        if not isinstance(check, dict):
            continue
        statements.append(
            f"INSERT INTO {native_table} "
            "(GENERATION_ID, CHECK_NAME, STATUS, DETAIL, REMEDIATION) VALUES ("
            f"{gid}, {_sql_literal(str(check.get('name') or 'native_app'))}, "
            f"{_sql_literal(str(check.get('status') or 'unknown'))}, "
            f"{_sql_literal(_native_check_detail(check))}, "
            f"{_sql_literal(str(check.get('remediation') or ''))})"
        )

    return statements


def _render_mismatch_sample_insert(
    table: str, gid: str, sample_type: str, row: dict[str, Any]
) -> str:
    entity_type = _sql_literal(str(row.get("entity_type") or "")) if "entity_type" in row else "NULL"
    relationship_type = (
        _sql_literal(str(row.get("relationship_type") or ""))
        if "relationship_type" in row
        else "NULL"
    )
    node_id = _sql_literal(str(row.get("nodeid") or "")) if "nodeid" in row else "NULL"
    edge_id = _sql_literal(str(row.get("edgeid") or "")) if "edgeid" in row else "NULL"
    source_node_id = (
        _sql_literal(str(row.get("sourcenodeid") or "")) if "sourcenodeid" in row else "NULL"
    )
    target_node_id = (
        _sql_literal(str(row.get("targetnodeid") or "")) if "targetnodeid" in row else "NULL"
    )
    return (
        f"INSERT INTO {table} "
        "(GENERATION_ID, SAMPLE_TYPE, ENTITY_TYPE, RELATIONSHIP_TYPE, NODE_ID, "
        "EDGE_ID, SOURCE_NODE_ID, TARGET_NODE_ID) VALUES ("
        f"{gid}, {_sql_literal(sample_type)}, {entity_type}, {relationship_type}, "
        f"{node_id}, {edge_id}, {source_node_id}, {target_node_id})"
    )


def _parity_status(row: dict[str, Any]) -> str:
    """Mirrors edgar_warehouse.mdm.graph_readonly._parity_status."""
    if _int(row.get("mdm_minus_graph")) or _int(row.get("graph_minus_mdm")):
        return "Mismatch"
    return "OK"


def _native_check_detail(check: dict[str, Any]) -> str:
    """Mirrors edgar_warehouse.mdm.graph_readonly._native_failure_detail,
    generalized to every check (not just failing ones)."""
    if "row_count" in check:
        return f"{_int(check.get('row_count'))} row(s) returned."
    return "Check ran before returning rows."


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


__all__ = [
    "DEFAULT_REVIEW_SCHEMA",
    "DEFAULT_GRAPH_SCHEMA",
    "GraphReviewPublishError",
    "resolve_active_generation_id",
    "publish_graph_review",
]
