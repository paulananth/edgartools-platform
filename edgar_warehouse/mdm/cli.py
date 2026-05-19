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
import time
from typing import Callable

from sqlalchemy.orm import Session

from edgar_warehouse.mdm.observability import elapsed_ms, emit_mdm_event


def register_mdm_subparser(subparsers: argparse._SubParsersAction) -> None:
    mdm = subparsers.add_parser("mdm", help="MDM pipeline, review, export operations")
    mdm_sub = mdm.add_subparsers(dest="mdm_command", required=True)

    migrate = mdm_sub.add_parser("migrate", help="Create/upgrade MDM schema and seed reference data")
    migrate.add_argument("--no-seed", dest="seed", action="store_false", default=True)
    migrate.set_defaults(handler=_logged_handler("migrate", _handle_migrate))

    counts = mdm_sub.add_parser("counts", help="Print MDM relational table row counts")
    counts.set_defaults(handler=_logged_handler("counts", _handle_counts))

    check = mdm_sub.add_parser("check-connectivity", help="Check MDM SQL and optional Neo4j connectivity")
    check.add_argument("--neo4j", action="store_true", help="Also check NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD")
    check.set_defaults(handler=_logged_handler("check-connectivity", _handle_check_connectivity))

    # run
    run = mdm_sub.add_parser("run", help="Run MDM pipeline for one or all domains")
    run.add_argument("--entity-type", choices=["company", "adviser", "security", "person", "fund", "all"], default="all")
    run.add_argument("--limit", type=int, default=None)
    run.set_defaults(handler=_logged_handler("run", _handle_run))

    sync = mdm_sub.add_parser("sync-graph", help="Sync pending MDM relationship rows to Neo4j")
    sync.add_argument("--limit", type=int, default=None)
    sync.add_argument("--limit-per-type", type=int, default=None, help="Maximum pending edges to sync for each relationship type")
    sync.add_argument("--relationship-type", action="append", default=None, help="Relationship type to sync; repeat for multiple types")
    sync.set_defaults(handler=_logged_handler("sync-graph", _handle_sync_graph))

    derive = mdm_sub.add_parser(
        "derive-relationships",
        help="Derive MDM relationship instances from resolved entities and silver facts",
    )
    derive.add_argument("--target-per-type", type=int, default=100, help="Active relationships to target per type")
    derive.add_argument("--relationship-type", action="append", default=None, help="Relationship type to derive; repeat for multiple types")
    derive.set_defaults(handler=_logged_handler("derive-relationships", _handle_derive_relationships))

    load_rels = mdm_sub.add_parser(
        "load-relationships",
        help="Resolve entities, derive relationships, and sync requested relationship targets to Neo4j",
    )
    load_rels.add_argument("--target-per-type", type=int, default=100, help="Active relationships to target per type")
    load_rels.add_argument("--entity-limit", type=int, default=None, help="Optional cap for each entity resolver phase")
    load_rels.add_argument("--relationship-type", action="append", default=None, help="Relationship type to load; repeat for multiple types")
    load_rels.add_argument("--skip-entity-resolution", action="store_true", default=False, help="Only derive/sync from existing MDM entities")
    load_rels.add_argument("--skip-graph-sync", action="store_true", default=False, help="Derive relationships but do not sync Neo4j")
    load_rels.set_defaults(handler=_logged_handler("load-relationships", _handle_load_relationships))

    api = mdm_sub.add_parser("api", help="Run the MDM FastAPI service with uvicorn")
    api.add_argument("--host", default="0.0.0.0")
    api.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    api.set_defaults(handler=_logged_handler("api", _handle_api))

    seed_u = mdm_sub.add_parser(
        "seed-universe",
        help="Seed tracked-universe CIKs from SEC company_tickers_exchange.json into MDM",
    )
    seed_u.add_argument("--limit", type=int, default=None, help="Cap rows upserted (for testing)")
    seed_u.add_argument(
        "--tracking-status",
        default="active",
        choices=["active", "bootstrap_pending", "paused"],
        help="tracking_status assigned to new companies (default: active)",
    )
    seed_u.set_defaults(handler=_logged_handler("seed-universe", _handle_seed_universe))

    seed_s = mdm_sub.add_parser(
        "seed-from-silver",
        help="One-time migration: copy tracking universe from silver DuckDB into MDM Postgres",
    )
    seed_s.add_argument(
        "--silver-path",
        default=None,
        help="Local path to silver.duckdb (default: download from WAREHOUSE_STORAGE_ROOT)",
    )
    seed_s.add_argument(
        "--tracking-status",
        default=None,
        help="Only migrate rows with this tracking_status (default: all rows)",
    )
    seed_s.add_argument("--dry-run", action="store_true", default=False, help="Print rows without writing to MDM")
    seed_s.set_defaults(handler=_logged_handler("seed-from-silver", _handle_seed_from_silver))

    # review
    rev = mdm_sub.add_parser("review", help="Curation queue operations")
    rev_sub = rev.add_subparsers(dest="review_command", required=True)

    rl = rev_sub.add_parser("list")
    rl.add_argument("--status", default="pending")
    rl.add_argument("--entity-type", default=None)
    rl.set_defaults(handler=_logged_handler("review-list", _handle_review_list))

    ra = rev_sub.add_parser("accept")
    ra.add_argument("review_id")
    ra.add_argument("--reviewer", default=os.environ.get("USER", "cli"))
    ra.set_defaults(handler=_logged_handler("review-accept", _handle_review_accept))

    rr = rev_sub.add_parser("reject")
    rr.add_argument("review_id")
    rr.add_argument("--reviewer", default=os.environ.get("USER", "cli"))
    rr.set_defaults(handler=_logged_handler("review-reject", _handle_review_reject))

    # quarantine / unquarantine
    q = mdm_sub.add_parser("quarantine")
    q.add_argument("entity_id")
    q.set_defaults(handler=_logged_handler("quarantine", _handle_quarantine))

    uq = mdm_sub.add_parser("unquarantine")
    uq.add_argument("entity_id")
    uq.set_defaults(handler=_logged_handler("unquarantine", _handle_unquarantine))

    # merge
    mg = mdm_sub.add_parser("merge")
    mg.add_argument("entity_id_keep")
    mg.add_argument("entity_id_discard")
    mg.add_argument("--reason", default="")
    mg.set_defaults(handler=_logged_handler("merge", _handle_merge))

    # verify-graph
    vg = mdm_sub.add_parser(
        "verify-graph",
        help="Query Neo4j for node and relationship counts and print JSON",
    )
    vg.set_defaults(handler=_logged_handler("verify-graph", _handle_verify_graph))

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
    br.set_defaults(handler=_logged_handler("backfill-relationships", _handle_backfill_relationships))

    # export
    ex = mdm_sub.add_parser("export")
    ex.add_argument("--since", default=None, help="ISO timestamp for incremental export")
    ex.add_argument("--entity-type", default=None)
    ex.add_argument("--batch-size", type=int, default=500)
    ex.set_defaults(handler=_logged_handler("export", _handle_export))


# -- shared helpers ---------------------------------------------------------

def _session() -> Session:
    from edgar_warehouse.mdm.database import get_engine, get_session
    return get_session(get_engine())


def _download_sec_bytes(url: str) -> bytes:
    from edgar_warehouse.infrastructure.sec_client import download_sec_bytes

    edgar_identity = os.environ.get("EDGAR_IDENTITY", "edgartools-platform contact@example.com")
    return download_sec_bytes(url, edgar_identity)


def _logged_handler(command_name: str, handler: Callable[[argparse.Namespace], int]) -> Callable[[argparse.Namespace], int]:
    def _wrapped(args: argparse.Namespace) -> int:
        started_at = time.monotonic()
        emit_mdm_event(
            "mdm_command_started",
            command=command_name,
            arguments=_safe_arguments(args),
        )
        try:
            exit_code = handler(args)
        except Exception as exc:
            emit_mdm_event(
                "mdm_command_failed",
                command=command_name,
                duration_ms=elapsed_ms(started_at),
                error=exc.__class__.__name__,
            )
            raise
        emit_mdm_event(
            "mdm_command_completed",
            command=command_name,
            duration_ms=elapsed_ms(started_at),
            exit_code=exit_code,
        )
        return exit_code

    return _wrapped


def _safe_arguments(args: argparse.Namespace) -> dict[str, object]:
    safe: dict[str, object] = {}
    blocked_fragments = ("password", "secret", "token", "key")
    for name, value in vars(args).items():
        if name == "handler" or any(fragment in name.lower() for fragment in blocked_fragments):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[name] = value
        elif isinstance(value, (list, tuple)):
            safe[name] = [str(item) for item in value]
        else:
            safe[name] = str(value)
    return safe


def _get_mdm_engine():
    from edgar_warehouse.mdm.database import get_engine
    return get_engine()


def _neo4j_client():
    from edgar_warehouse.mdm.graph import Neo4jGraphClient

    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER") or os.environ.get("NEO4J_USERNAME")
    password = os.environ.get("NEO4J_PASSWORD")
    database = os.environ.get("NEO4J_DATABASE")
    if not (uri and user and password) and os.environ.get("NEO4J_SECRET_JSON"):
        payload = json.loads(os.environ["NEO4J_SECRET_JSON"])
        uri = uri or payload.get("uri")
        user = user or payload.get("user") or payload.get("username")
        password = password or payload.get("password")
        database = database or payload.get("database")
    if not (uri and user and password):
        return None
    # neo4j:// triggers bolt routing which fails on single-instance deployments
    # without NEO4J_server_bolt_advertised__address configured; use bolt:// directly.
    if uri and uri.startswith("neo4j://"):
        uri = "bolt://" + uri[len("neo4j://"):]
    return Neo4jGraphClient(uri=uri, user=user, password=password, database=database)


def _silver_reader():
    """Thin DuckDB reader. Returns None when MDM_SILVER_DUCKDB is absent or empty."""
    duckdb_path = os.environ.get("MDM_SILVER_DUCKDB") or None
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


# -- silver preflight helpers -----------------------------------------------

# Fixed allowlist of required tables per entity type for 'mdm run'.
# Values are True = table must be nonempty; False = table must exist (any count).
# T-05-14: No operator-provided table name is ever used here.
_REQUIRED_TABLES_RUN: dict[str, dict[str, bool]] = {
    "company": {
        "sec_company": False,  # must exist; ticker/sync-state are optional
    },
    "adviser": {
        "sec_adv_filing": True,  # nonempty
    },
    "fund": {
        "sec_adv_private_fund": True,  # nonempty
    },
    "person": {
        "sec_company_filing": True,  # nonempty
        "sec_ownership_reporting_owner": True,  # nonempty
    },
    "security": {
        "sec_company_filing": True,  # nonempty
        "sec_ownership_non_derivative_txn": True,  # nonempty
    },
}

# Fixed required tables for 'derive-relationships' and 'load-relationships' (D-12).
_REQUIRED_TABLES_RELATIONSHIPS: dict[str, bool] = {
    "sec_company": True,
    "sec_company_filing": True,
    "sec_ownership_reporting_owner": True,
}


def _required_tables_for_run(entity_type: str) -> dict[str, bool]:
    """Return the fixed required-table mapping for the given entity type."""
    if entity_type == "all":
        merged: dict[str, bool] = {}
        for tables in _REQUIRED_TABLES_RUN.values():
            for table, must_be_nonempty in tables.items():
                # If the table already in merged, keep the stricter requirement.
                existing = merged.get(table, False)
                merged[table] = existing or must_be_nonempty
        return merged
    return _REQUIRED_TABLES_RUN.get(entity_type, {})


def _validate_silver_tables(reader, required_tables: dict[str, bool]) -> list[str]:
    """Check required tables exist and have the required row counts.

    Uses only fixed table-name constants from the allowlist — no user-controlled
    identifiers are interpolated into SQL (T-05-14).

    Returns a list of human-readable failure descriptions (empty = all passed).
    """
    import duckdb  # type: ignore

    failures: list[str] = []
    for table_name, must_be_nonempty in required_tables.items():
        # Security: table_name comes exclusively from the fixed _REQUIRED_TABLES_*
        # constants above; never from args, env, or external input.
        try:
            rows = reader.fetch(
                f"SELECT COUNT(*) AS n FROM {table_name}"  # noqa: S608
            )
            count = rows[0]["n"] if rows else 0
            if must_be_nonempty and count == 0:
                failures.append(f"required table '{table_name}' is empty (0 rows)")
        except Exception as exc:
            err_lower = str(exc).lower()
            if "not found" in err_lower or "binder" in err_lower or "catalog" in err_lower or "does not exist" in err_lower:
                failures.append(f"required table '{table_name}' is missing from silver DuckDB")
            else:
                failures.append(f"required table '{table_name}' could not be queried: {exc}")
    return failures


def _require_silver_reader(
    required_tables: dict[str, bool],
    command_name: str,
) -> tuple:
    """Open the silver DuckDB reader and validate required tables.

    Runs source preflight BEFORE any MDM session is opened (D-11, T-05-15).
    Returns (reader, 0) on success or (None, 1) on any failure.
    Prints actionable stderr naming MDM_SILVER_DUCKDB on failure.
    """
    try:
        reader = _silver_reader()
    except Exception as exc:
        print(
            f"{command_name}: cannot open MDM_SILVER_DUCKDB — {exc}. "
            "Check that MDM_SILVER_DUCKDB is set to a valid local path or s3:// URI.",
            file=sys.stderr,
        )
        return None, 1

    if reader is None:
        print(
            f"{command_name}: MDM_SILVER_DUCKDB is required but is not set. "
            "Set MDM_SILVER_DUCKDB to a local DuckDB path or s3:// URI.",
            file=sys.stderr,
        )
        return None, 1

    if required_tables:
        failures = _validate_silver_tables(reader, required_tables)
        if failures:
            print(
                f"{command_name}: silver DuckDB source is not ready. "
                + "; ".join(failures),
                file=sys.stderr,
            )
            return None, 1

    return reader, 0


# -- handlers ---------------------------------------------------------------

def _handle_run(args) -> int:
    from edgar_warehouse.mdm.pipeline import MDMPipeline

    required = _required_tables_for_run(args.entity_type)
    silver, rc = _require_silver_reader(required, "mdm run")
    if rc != 0:
        return rc

    session = _session()
    try:
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
        if args.entity_type == "security":
            n = pipeline.run_securities(limit=args.limit)
            print(f"securities: {n}")
        if args.entity_type == "person":
            n = pipeline.run_persons(limit=args.limit)
            print(f"persons: {n}")
        if args.entity_type == "fund":
            n = pipeline.run_funds(limit=args.limit)
            print(f"funds: {n}")
        return 0
    finally:
        session.close()


def _handle_seed_universe(args) -> int:
    from edgar_warehouse.loaders import seed_universe_loader
    from edgar_warehouse.mdm.universe import bulk_upsert_universe

    url = "https://www.sec.gov/files/company_tickers_exchange.json"
    payload = json.loads(_download_sec_bytes(url))
    rows = seed_universe_loader(
        payload,
        sync_run_id="mdm-seed-universe",
        raw_object_id="",
        load_mode="seed_universe",
    )
    if args.limit is not None:
        rows = rows[: args.limit]

    engine = _get_mdm_engine()
    count = bulk_upsert_universe(engine, rows, default_status=args.tracking_status)
    print(json.dumps({"rows_seeded": count, "status": "ok"}, indent=2))
    return 0


def _handle_seed_from_silver(args) -> int:
    """Migrate company tracking universe from silver DuckDB into MDM Postgres.

    Reads sec_tracked_universe rows from a silver DuckDB file (local path or
    downloaded from S3 via WAREHOUSE_STORAGE_ROOT) and upserts them into
    mdm_company, preserving existing tracking_status values in MDM.
    """
    import os
    import tempfile
    try:
        import duckdb
    except ImportError as exc:
        raise SystemExit("duckdb is required for seed-from-silver. Install with: uv pip install duckdb") from exc

    from edgar_warehouse.mdm.universe import bulk_upsert_universe

    silver_path = getattr(args, "silver_path", None)
    if not silver_path:
        storage_root = os.environ.get("WAREHOUSE_STORAGE_ROOT", "").strip()
        if not storage_root:
            raise SystemExit("--silver-path or WAREHOUSE_STORAGE_ROOT is required")
        s3_uri = storage_root.rstrip("/") + "/silver/sec/silver.duckdb"
        tmp = tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False)
        tmp.close()
        silver_path = tmp.name
        print(json.dumps({"status": "downloading", "source": s3_uri}))
        import boto3
        # Parse s3://bucket/key
        s3_parts = s3_uri[len("s3://"):].split("/", 1)
        s3_bucket, s3_key = s3_parts[0], s3_parts[1]
        region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
        boto3.client("s3", region_name=region).download_file(s3_bucket, s3_key, silver_path)

    tracking_status_filter = getattr(args, "tracking_status", None)
    dry_run = bool(getattr(args, "dry_run", False))

    con = duckdb.connect(silver_path, read_only=True)
    try:
        query = "SELECT cik, current_ticker, NULL as exchange, tracking_status FROM sec_tracked_universe"
        params: list = []
        if tracking_status_filter:
            query += " WHERE tracking_status = ?"
            params.append(tracking_status_filter)
        silver_rows = con.execute(query, params).fetchall()
    finally:
        con.close()

    if not silver_rows:
        print(json.dumps({"status": "ok", "rows_found": 0, "rows_migrated": 0}))
        return 0

    migrate_rows = [
        {"cik": r[0], "ticker": r[1] or str(r[0]), "exchange": r[2]}
        for r in silver_rows
    ]
    status_groups: dict[str, int] = {}
    for r in silver_rows:
        status_groups[r[3]] = status_groups.get(r[3], 0) + 1

    if dry_run:
        print(json.dumps({"status": "dry_run", "rows_found": len(migrate_rows), "by_status": status_groups}, indent=2))
        return 0

    engine = _get_mdm_engine()
    total = 0
    for status, rows_for_status in _group_by_status(silver_rows):
        upsert_rows = [{"cik": r[0], "ticker": r[1] or str(r[0]), "exchange": r[2]} for r in rows_for_status]
        total += bulk_upsert_universe(engine, upsert_rows, default_status=status)

    print(json.dumps({"status": "ok", "rows_found": len(migrate_rows), "rows_migrated": total, "by_status": status_groups}, indent=2))
    return 0


def _group_by_status(rows: list) -> list[tuple[str, list]]:
    groups: dict[str, list] = {}
    for r in rows:
        status = r[3] or "active"
        groups.setdefault(status, []).append(r)
    return list(groups.items())


def _handle_migrate(args) -> int:
    from edgar_warehouse.mdm.database import get_engine
    from edgar_warehouse.mdm.migrations.runtime import migrate

    payload = migrate(get_engine(), seed=args.seed)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _handle_counts(args) -> int:
    from edgar_warehouse.mdm.database import get_engine
    from edgar_warehouse.mdm.migrations.runtime import count_tables

    engine = get_engine()
    payload = dict(count_tables(engine))
    with Session(engine) as session:
        payload["relationships_by_type"] = _relationship_counts_by_type(session)
    print(json.dumps(payload, indent=2, sort_keys=True))
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
        sync = GraphSyncEngine.build(session, client)
        node_count = sync.sync_entities(limit=args.limit)
        edge_count = sync.sync_pending(
            limit=args.limit,
            relationship_types=args.relationship_type,
            limit_per_type=args.limit_per_type,
        )
        session.commit()
    finally:
        client.close()
        session.close()
    print(json.dumps({"graph_edges_synced": edge_count, "graph_nodes_synced": node_count}, indent=2, sort_keys=True))
    return 0


def _handle_derive_relationships(args) -> int:
    from edgar_warehouse.mdm.pipeline import MDMPipeline

    silver, rc = _require_silver_reader(_REQUIRED_TABLES_RELATIONSHIPS, "mdm derive-relationships")
    if rc != 0:
        return rc

    session = _session()
    try:
        pipeline = MDMPipeline(session=session, silver=silver)
        summary = pipeline.derive_relationships(
            target_per_type=args.target_per_type,
            relationship_types=args.relationship_type,
        )
        session.commit()
    finally:
        session.close()
    print(json.dumps({"relationship_counts_by_type": summary}, indent=2, sort_keys=True))
    return 0


def _handle_load_relationships(args) -> int:
    from edgar_warehouse.mdm.graph import GraphSyncEngine
    from edgar_warehouse.mdm.pipeline import MDMPipeline

    silver, rc = _require_silver_reader(_REQUIRED_TABLES_RELATIONSHIPS, "mdm load-relationships")
    if rc != 0:
        return rc

    client = None if args.skip_graph_sync else _neo4j_client()
    session = _session()
    try:
        pipeline = MDMPipeline(session=session, silver=silver, neo4j=client)
        entity_counts: dict[str, int] = {}
        if not args.skip_entity_resolution:
            entity_counts = {
                "companies_processed": pipeline.run_companies(limit=args.entity_limit),
                "advisers_processed": pipeline.run_advisers(limit=args.entity_limit),
                "securities_processed": pipeline.run_securities(limit=args.entity_limit),
                "persons_processed": pipeline.run_persons(limit=args.entity_limit),
                "funds_processed": pipeline.run_funds(limit=args.entity_limit),
            }
        relationship_summary = pipeline.derive_relationships(
            target_per_type=args.target_per_type,
            relationship_types=args.relationship_type,
        )
        graph_nodes_synced = 0
        graph_edges_synced = 0
        if client is not None:
            sync = GraphSyncEngine.build(session, client)
            graph_nodes_synced = sync.sync_entities()
            graph_edges_synced = sync.sync_pending(
                relationship_types=args.relationship_type,
                limit_per_type=args.target_per_type,
            )
        session.commit()
    finally:
        if client is not None:
            client.close()
        session.close()

    print(
        json.dumps(
            {
                **entity_counts,
                "graph_edges_synced": graph_edges_synced,
                "graph_nodes_synced": graph_nodes_synced,
                "relationship_counts_by_type": relationship_summary,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _handle_verify_graph(args) -> int:
    client = _neo4j_client()
    if client is None:
        print(json.dumps({"error": "NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD not configured"}), file=sys.stderr)
        return 1
    session = _session()
    try:
        from edgar_warehouse.mdm.graph import GraphRegistry, GraphSyncEngine

        registry = GraphRegistry.load(session)
        relationship_types = sorted(registry.rel_type_by_name)
        with client.session() as s:
            payload = {"neo4j_nodes_total": s.run("MATCH (n) RETURN count(n) AS n").single()["n"]}
            for rel_type in relationship_types:
                _validate_cypher_relationship_type(rel_type)
                payload[f"neo4j_{rel_type}_edges"] = s.run(
                    f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS n"
                ).single()["n"]
        # Add pending MDM counts (SQL only — Neo4j connection already released)
        engine = GraphSyncEngine(session=session, registry=registry)
        pending = engine.pending_counts()
        for rel_type in relationship_types:
            payload[f"mdm_{rel_type}_pending"] = pending.get(rel_type, 0)
    finally:
        session.close()
        client.close()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _handle_backfill_relationships(args) -> int:
    from edgar_warehouse.mdm.graph import backfill_relationship_instances
    from edgar_warehouse.mdm.pipeline import MDMPipeline
    from edgar_warehouse.mdm.rules import MDMRuleEngine

    session = _session()
    client = _neo4j_client()
    silver = _silver_reader()
    try:
        # Phase 1: repair mdm_security.issuer_entity_id = NULL rows before deriving ISSUED_BY.
        # Root cause: run_companies(limit=100) may not have processed a security's issuer on the
        # run it was first created, leaving issuer_entity_id NULL permanently.
        issuers_repaired = 0
        if silver is not None:
            pipeline = MDMPipeline(session=session, silver=silver)
            issuers_repaired = pipeline.backfill_security_issuers()

        # Phase 2: derive MANAGES_FUND and ISSUED_BY instances, sync to Neo4j.
        result = backfill_relationship_instances(session, neo4j=client, limit=args.limit)
        result["issuers_repaired"] = issuers_repaired
    finally:
        if client is not None:
            client.close()
        session.close()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _relationship_counts_by_type(session: Session) -> dict[str, dict[str, int]]:
    from sqlalchemy import case, func, select
    from edgar_warehouse.mdm.database import MdmRelationshipInstance, MdmRelationshipType

    pending_expr = case(
        (
            (MdmRelationshipInstance.instance_id.isnot(None))
            & (MdmRelationshipInstance.graph_synced_at.is_(None)),
            1,
        ),
        else_=0,
    )
    rows = session.execute(
        select(
            MdmRelationshipType.rel_type_name,
            func.count(MdmRelationshipInstance.instance_id),
            func.coalesce(func.sum(pending_expr), 0),
        )
        .outerjoin(
            MdmRelationshipInstance,
            (MdmRelationshipInstance.rel_type_id == MdmRelationshipType.rel_type_id)
            & (MdmRelationshipInstance.is_active == True),
        )
        .where(MdmRelationshipType.is_active == True)
        .group_by(MdmRelationshipType.rel_type_name)
        .order_by(MdmRelationshipType.rel_type_name)
    )
    return {
        name: {"active": int(active or 0), "pending_graph_sync": int(pending or 0)}
        for name, active, pending in rows
    }


def _validate_cypher_relationship_type(rel_type: str) -> None:
    if not rel_type.replace("_", "").isalnum() or not rel_type[0].isalpha():
        raise ValueError(f"Unsafe Neo4j relationship type: {rel_type}")


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
