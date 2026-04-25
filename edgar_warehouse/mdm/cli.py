"""CLI subcommand: `edgar-warehouse mdm ...`.

Attaches to the existing argparse parser in edgar_warehouse/cli.py via
register_mdm_subparser.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Callable

from sqlalchemy.orm import Session


def register_mdm_subparser(subparsers: argparse._SubParsersAction) -> None:
    mdm = subparsers.add_parser("mdm", help="MDM pipeline, review, export operations")
    mdm_sub = mdm.add_subparsers(dest="mdm_command", required=True)

    # run
    run = mdm_sub.add_parser("run", help="Run MDM pipeline for one or all domains")
    run.add_argument("--entity-type", choices=["company", "adviser", "all"], default="all")
    run.add_argument("--limit", type=int, default=None)
    run.set_defaults(handler=_handle_run)

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


def _silver_reader():
    """Thin DuckDB reader. Returns None in local/dev mode so CLI shows intent only."""
    duckdb_path = os.environ.get("MDM_SILVER_DUCKDB")
    if duckdb_path is None:
        return None
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

    pipeline = MDMPipeline(session=session, silver=silver)
    if args.entity_type in ("all", "company"):
        n = pipeline.run_companies(limit=args.limit)
        print(f"companies: {n}")
    if args.entity_type in ("all", "adviser"):
        n = pipeline.run_advisers(limit=args.limit)
        print(f"advisers: {n}")
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
