"""CLI subcommand: `edgar-warehouse mdm ...`.

Attaches to the existing argparse parser in edgar_warehouse/cli.py via
register_mdm_subparser.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from sqlalchemy.orm import Session


def register_mdm_subparser(subparsers: argparse._SubParsersAction) -> None:
    mdm = subparsers.add_parser("mdm", help="MDM pipeline, review, export operations")
    mdm_sub = mdm.add_subparsers(dest="mdm_command", required=True)

    migrate = mdm_sub.add_parser("migrate", help="Create/upgrade MDM schema and seed reference data")
    migrate.add_argument("--no-seed", dest="seed", action="store_false", default=True)
    migrate.set_defaults(handler=_handle_migrate)

    counts = mdm_sub.add_parser("counts", help="Print MDM relational table row counts")
    counts.set_defaults(handler=_handle_counts)

    check = mdm_sub.add_parser("check-connectivity", help="Check MDM SQL and optional Neo4j connectivity")
    check.add_argument("--neo4j", action="store_true", help="Also check NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD")
    check.set_defaults(handler=_handle_check_connectivity)

    # run
    run = mdm_sub.add_parser("run", help="Run MDM pipeline for one or all domains")
    run.add_argument("--entity-type", choices=["company", "adviser", "all"], default="all")
    run.add_argument("--limit", type=int, default=None)
    run.set_defaults(handler=_handle_run)

    sync = mdm_sub.add_parser("sync-graph", help="Sync pending MDM relationship rows to Neo4j")
    sync.add_argument("--limit", type=int, default=None)
    sync.set_defaults(handler=_handle_sync_graph)

    api = mdm_sub.add_parser("api", help="Run the MDM FastAPI service with uvicorn")
    api.add_argument("--host", default="0.0.0.0")
    api.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    api.set_defaults(handler=_handle_api)


    # review
    rev = mdm_sub.add_parser("review", help="Curation queue operations")
    rev_sub = rev.add_subparsers(dest="review_command", required=True)

    rl = rev_sub.add_parser("list")
    rl.add_argument("--status", default="pending")
    rl.add_argument("--entity-type", default=None)
    rl.set_defaults(handler=_handle_review_list)

    ra = rev_sub.add_parser("accept")
    ra.add_argument("review_id")
    ra.add_argument("--reviewer", default=os.environ.get("USER", "cli"))
    ra.set_defaults(handler=_handle_review_accept)

    rr = rev_sub.add_parser("reject")
    rr.add_argument("review_id")
    rr.add_argument("--reviewer", default=os.environ.get("USER", "cli"))
    rr.set_defaults(handler=_handle_review_reject)

    # quarantine / unquarantine
    q = mdm_sub.add_parser("quarantine")
    q.add_argument("entity_id")
    q.set_defaults(handler=_handle_quarantine)

    uq = mdm_sub.add_parser("unquarantine")
    uq.add_argument("entity_id")
    uq.set_defaults(handler=_handle_unquarantine)

    # merge
    mg = mdm_sub.add_parser("merge")
    mg.add_argument("entity_id_keep")
    mg.add_argument("entity_id_discard")
    mg.add_argument("--reason", default="")
    mg.set_defaults(handler=_handle_merge)

    # verify-graph
    vg = mdm_sub.add_parser(
        "verify-graph",
        help="Query Neo4j for node and relationship counts and print JSON",
    )
    vg.set_defaults(handler=_handle_verify_graph)

    # backfill-relationships
    br = mdm_sub.add_parser(
        "backfill-relationships",
        help="Derive relationship instances from mdm_fund/mdm_security and sync to Neo4j",
    )
    br.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of relationship instances to backfill and sync (default: 100)",
    )
    br.set_defaults(handler=_handle_backfill_relationships)

    # export
    ex = mdm_sub.add_parser("export")
    ex.add_argument("--since", default=None, help="ISO timestamp for incremental export")
    ex.add_argument("--entity-type", default=None)
    ex.add_argument("--batch-size", type=int, default=500)
    ex.set_defaults(handler=_handle_export)


# -- shared helpers ---------------------------------------------------------

def _session() -> Session:
    from edgar_warehouse.mdm.database import get_engine, get_session
    return get_session(get_engine())


def _neo4j_client():
    from edgar_warehouse.mdm.graph import Neo4jGraphClient

    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER")
    password = os.environ.get("NEO4J_PASSWORD")
    if not (uri and user and password) and os.environ.get("NEO4J_SECRET_JSON"):
        payload = json.loads(os.environ["NEO4J_SECRET_JSON"])
        uri = uri or payload.get("uri")
        user = user or payload.get("user")
        password = password or payload.get("password")
    if not (uri and user and password):
        return None
    # neo4j:// triggers bolt routing which fails on single-instance deployments
    # without NEO4J_server_bolt_advertised__address configured; use bolt:// directly.
    if uri and uri.startswith("neo4j://"):
        uri = "bolt://" + uri[len("neo4j://"):]
    return Neo4jGraphClient(uri=uri, user=user, password=password)


def _silver_reader():
    """Thin DuckDB reader. Returns None in local/dev mode so CLI shows intent only."""
    duckdb_path = os.environ.get("MDM_SILVER_DUCKDB")
    if duckdb_path is None:
        return None
    if "://" in duckdb_path:
        from edgar_warehouse.infrastructure.object_storage import read_bytes

        local_path = Path(os.environ.get("MDM_LOCAL_SILVER_DUCKDB", "/tmp/mdm-silver.duckdb"))
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(read_bytes(duckdb_path))
        duckdb_path = str(local_path)
    import duckdb  # type: ignore

    class _DuckReader:
        def __init__(self, path: str) -> None:
            self._con = duckdb.connect(path, read_only=True)

        def fetch(self, sql: str, params: list | None = None) -> list[dict]:
            rows = self._con.execute(sql, params or []).fetchall()
            cols = [d[0] for d in self._con.description]
            return [dict(zip(cols, r)) for r in rows]

    return _DuckReader(duckdb_path)


# -- handlers ---------------------------------------------------------------

def _handle_run(args) -> int:
    from edgar_warehouse.mdm.pipeline import MDMPipeline

    session = _session()
    silver = _silver_reader()
    if silver is None:
        print("MDM_SILVER_DUCKDB not set; nothing to do.", file=sys.stderr)
        return 1

    pipeline = MDMPipeline(session=session, silver=silver, neo4j=_neo4j_client())
    if args.entity_type == "all":
        stats = pipeline.run_all(limit=args.limit)
        print(json.dumps(stats.__dict__, indent=2, sort_keys=True))
        return 0
    if args.entity_type == "company":
        n = pipeline.run_companies(limit=args.limit)
        print(f"companies: {n}")
    if args.entity_type == "adviser":
        n = pipeline.run_advisers(limit=args.limit)
        print(f"advisers: {n}")
    return 0


def _handle_migrate(args) -> int:
    from edgar_warehouse.mdm.database import get_engine
    from edgar_warehouse.mdm.migrations.runtime import migrate

    payload = migrate(get_engine(), seed=args.seed)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _handle_counts(args) -> int:
    from edgar_warehouse.mdm.database import get_engine
    from edgar_warehouse.mdm.migrations.runtime import count_tables

    print(json.dumps(count_tables(get_engine()), indent=2, sort_keys=True))
    return 0


def _handle_check_connectivity(args) -> int:
    from edgar_warehouse.mdm.database import get_engine
    from edgar_warehouse.mdm.migrations.runtime import check_connectivity

    payload = {"sql": check_connectivity(get_engine())}
    if args.neo4j:
        client = _neo4j_client()
        if client is None:
            payload["neo4j"] = {"connected": False, "error": "NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD not configured"}
        else:
            try:
                with client.session() as session:
                    record = session.run("RETURN 1 AS ok").single()
                payload["neo4j"] = {"connected": bool(record and record["ok"] == 1)}
            finally:
                client.close()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _handle_sync_graph(args) -> int:
    from edgar_warehouse.mdm.graph import GraphSyncEngine

    client = _neo4j_client()
    if client is None:
        print("NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD not configured", file=sys.stderr)
        return 1
    session = _session()
    try:
        count = GraphSyncEngine.build(session, client).sync_pending(limit=args.limit)
        session.commit()
    finally:
        client.close()
        session.close()
    print(json.dumps({"graph_edges_synced": count}, indent=2, sort_keys=True))
    return 0


def _handle_verify_graph(args) -> int:
    client = _neo4j_client()
    if client is None:
        print(json.dumps({"error": "NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD not configured"}), file=sys.stderr)
        return 1
    try:
        with client.session() as s:
            nodes   = s.run("MATCH (n)                    RETURN count(n) AS n").single()["n"]
            manages = s.run("MATCH ()-[r:MANAGES_FUND]->() RETURN count(r) AS n").single()["n"]
            issued  = s.run("MATCH ()-[r:ISSUED_BY]->()   RETURN count(r) AS n").single()["n"]
    finally:
        client.close()
    print(json.dumps({
        "neo4j_nodes_total":        nodes,
        "neo4j_MANAGES_FUND_edges": manages,
        "neo4j_ISSUED_BY_edges":    issued,
    }, indent=2, sort_keys=True))
    return 0


def _handle_backfill_relationships(args) -> int:
    from edgar_warehouse.mdm.graph import backfill_relationship_instances

    session = _session()
    client = _neo4j_client()
    try:
        result = backfill_relationship_instances(session, neo4j=client, limit=args.limit)
    finally:
        if client is not None:
            client.close()
        session.close()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _handle_api(args) -> int:
    import uvicorn

    uvicorn.run("edgar_warehouse.mdm.api.main:app", host=args.host, port=args.port)
    return 0


def _handle_review_list(args) -> int:
    from edgar_warehouse.mdm.stewardship import list_pending_reviews

    rows = list_pending_reviews(_session(), entity_type=args.entity_type)
    for r in rows:
        print(f"{r.review_id}  score={r.match_score:.2f}  a={r.entity_id_a}  b={r.entity_id_b}")
    return 0


def _handle_review_accept(args) -> int:
    from edgar_warehouse.mdm.stewardship import accept_review
    kept = accept_review(_session(), args.review_id, args.reviewer)
    print(f"accepted; kept entity={kept}")
    return 0


def _handle_review_reject(args) -> int:
    from edgar_warehouse.mdm.stewardship import reject_review
    reject_review(_session(), args.review_id, args.reviewer)
    print("rejected")
    return 0


def _handle_quarantine(args) -> int:
    from edgar_warehouse.mdm.stewardship import quarantine
    quarantine(_session(), args.entity_id)
    print(f"quarantined {args.entity_id}")
    return 0


def _handle_unquarantine(args) -> int:
    from edgar_warehouse.mdm.stewardship import unquarantine
    unquarantine(_session(), args.entity_id)
    print(f"unquarantined {args.entity_id}")
    return 0


def _handle_merge(args) -> int:
    from edgar_warehouse.mdm.stewardship import merge_entities
    merge_entities(_session(), keep=args.entity_id_keep, discard=args.entity_id_discard,
                   reason=args.reason)
    print(f"merged {args.entity_id_discard} -> {args.entity_id_keep}")
    return 0


def _handle_export(args) -> int:
    from datetime import datetime

    from edgar_warehouse.mdm.export import MDMExporter

    writer = _build_snowflake_writer()
    exporter = MDMExporter(session=_session(), writer=writer)
    since = datetime.fromisoformat(args.since) if args.since else None
    n = exporter.export_pending(since=since, entity_type=args.entity_type,
                                batch_size=args.batch_size)
    print(f"exported {n} rows")
    return 0


def _build_snowflake_writer():
    """Deferred — real writer uses snowflake-connector-python; stub here raises."""

    class _StubWriter:
        def upsert(self, table, rows, key="entity_id"):
            raise RuntimeError(
                "Snowflake writer not configured. Wire one via "
                "edgar_warehouse.mdm.export.SnowflakeWriter in infra."
            )

    return _StubWriter()
