"""`edgar-warehouse silver`: migrate the silver schema, register a silver table
spec as a table, land a part's rows into it, and describe a table for an agent.

Connections come from the environment and are never printed:
SILVER_MIGRATION_DATABASE_URL (the schema owner, for init, migrate and register),
SILVER_DATABASE_URL (the restricted runtime login, for land and describe) and
MDM_DATABASE_URL (read, for the MDM ids of a table that links to masters).
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _handle(args):
    from sqlalchemy import create_engine

    from . import database
    from .rows import records
    from .sink import PostgresSink
    from .writer import MdmIds, land, refresh_ids

    engines = []

    def engine(variable):
        value = create_engine(os.environ[variable])
        engines.append(value)
        return value

    try:
        if args.silver_command in {"init", "migrate"}:
            result = database.migrate(engine("SILVER_MIGRATION_DATABASE_URL"), runtime_role=args.runtime_role,
                                      existing_only=args.silver_command == "migrate")
        elif args.silver_command == "register":
            result = database.register(engine("SILVER_MIGRATION_DATABASE_URL"), spec_file(args.spec, args.part),
                                       runtime_role=args.runtime_role)
        elif args.silver_command in {"land", "refresh-ids"}:
            ids = MdmIds(engine("MDM_DATABASE_URL")) if os.environ.get("MDM_DATABASE_URL") else None
            sink = PostgresSink(engine("SILVER_DATABASE_URL"))
            result = (land(sink, args.table, records(args.rows), ids) if args.silver_command == "land"
                      else refresh_ids(sink, args.table, ids))
        else:
            from .context import TableContext

            result = TableContext(engine("SILVER_DATABASE_URL")).table(args.table)
    finally:
        for value in engines:
            value.dispose()
    print(json.dumps(result, default=str, sort_keys=True, indent=2))
    return 0


def spec_file(path: Path, part: str | None) -> dict:
    """A silver table spec from a JSON or YAML file: the spec itself, or the
    findings.yaml profiling wrote, with --part naming the part whose spec to use."""
    from edgar_warehouse.control_contract import Blocked
    from edgar_warehouse.rules.files import load

    body = load(Path(path)) if Path(path).suffix in {".yaml", ".yml"} else json.loads(Path(path).read_text())
    if isinstance(body, dict) and "parts" in body:
        if not part:
            raise Blocked("A findings file holds many parts: name one with --part")
        found = [p for p in body["parts"] if p.get("part") == part]
        if not found or not found[0].get("silver"):
            raise Blocked(f"Part {part} has no silver spec in {Path(path).name}")
        return found[0]["silver"]
    if part:
        raise Blocked("--part reads a findings file; this file is one spec")
    return body


def _commands(parser):
    commands = parser.add_subparsers(dest="silver_command", required=True)
    for name in ("init", "migrate"):
        command = commands.add_parser(name)
        command.add_argument("--runtime-role", required=True)
        command.set_defaults(handler=_handle)
    registered = commands.add_parser("register", help="Create a silver table from an approved silver table spec")
    registered.add_argument("spec", type=Path, help="A spec file (JSON or YAML), or a findings.yaml with --part")
    registered.add_argument("--part", help="The part whose silver spec to use, when the file is a findings.yaml")
    registered.add_argument("--runtime-role", required=True)
    registered.set_defaults(handler=_handle)
    landed = commands.add_parser("land", help="Write a part's rows into its silver table, with MDM ids for its links")
    landed.add_argument("table")
    landed.add_argument("rows", type=Path, help="Flat rows: a .jsonl, .csv or .parquet file")
    landed.set_defaults(handler=_handle)
    refreshed = commands.add_parser("refresh-ids", help="Fill the MDM ids of rows already landed, from MDM as it is now")
    refreshed.add_argument("table")
    refreshed.set_defaults(handler=_handle)
    described = commands.add_parser("describe", help="A silver table for an agent: grain, key, links, time, load mode")
    described.add_argument("table", nargs="?")
    described.set_defaults(handler=_handle)
    return commands


def register(subparsers):
    parser = subparsers.add_parser("silver", help="Silver tables made from profiling's silver table specs")
    return _commands(parser)
